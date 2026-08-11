# ADR 010: Measure the complete HTTP path with isolated load levels

- Status: accepted
- Date: 2026-08-11

## Context

The original latency benchmark called the Python service directly and sequentially. It was
useful for profiling inference, but excluded HTTP parsing, server scheduling, concurrent
contention, and the durable journal. It could not support a throughput statement.

## Alternatives considered

1. Report only the in-process benchmark. Fast and deterministic, but incomplete.
2. Add an external load-testing platform. Realistic, but not one-command reproducible and
   sensitive to infrastructure that is outside this repository.
3. Launch a real local Uvicorn process and drive it with a pooled asynchronous HTTP client.

## Decision

Use option 3. `make load-benchmark` measures concurrency 1, 4, 8, and 16. Each level gets a
fresh single-worker process and fresh SQLite database, 25 excluded warmups, and 500 measured
requests. Raw request latency and status are saved to CSV; environment, commit, protocol,
throughput, errors, and percentiles are saved to JSON; the chart is generated from that JSON.

## Advantages

- The request path includes validation, features, graph, both models, explanation, JSON, and
  SQLite WAL/full-sync persistence.
- Fresh state per level avoids graph growth and database history confounding concurrency.
- The benchmark itself has a two-request real-server integration test in CI.

## Disadvantages

- Client and server share one host and communicate over loopback.
- There is no TLS, reverse proxy, container, remote network, or multiple worker process.
- Five hundred requests per level are insufficient for a production SLO claim.
- The service's global state lock deliberately serializes mutation and limits concurrency.

## Consequences

Results describe this workstation and protocol only. They expose the single-process
contention curve and establish a repeatable baseline; they do not establish scale,
capacity, or production readiness. A distributed successor should repeat the same raw-data
contract under remote, sustained, failure-injected workloads.
