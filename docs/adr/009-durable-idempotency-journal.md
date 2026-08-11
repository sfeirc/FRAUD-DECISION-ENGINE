# ADR 009: Durable idempotency and authorization journal in SQLite

- Status: accepted
- Date: 2026-08-11

## Context

Payment clients retry when responses time out. Reapplying a retry to temporal and graph state
would double-count the payment and could return a different decision. The v0.2 audit deque
also disappeared on restart, and out-of-order events had no explicit policy.

## Alternatives considered

1. Keep process-local state and document at-most-once caller behavior. This pushes an unsafe
   requirement onto clients and does not survive restarts.
2. Require Kafka plus a distributed database. This can support horizontal processing, but it
   would make the local reference system operationally heavy without demonstrating those
   distributed guarantees.
3. Add a transactional SQLite journal for the single-process reference architecture.

## Decision

Use option 3. The transaction ID is the idempotency key. An exact retry returns the persisted
response without mutating features or the graph; reuse with a different request hash returns
HTTP 409. SQLite uses WAL and full synchronous writes. Per-customer event-time watermarks
reject events more than five minutes late with HTTP 409. Docker Compose mounts the database
on a named volume. The audit endpoint reads the journal, and `/metrics` exposes decision,
review-queue, and latency series in Prometheus text format.

## Advantages

- Exact retries are stable across process restarts.
- Authorization decisions and explanations are queryable after restart.
- The late-event policy is explicit and tested rather than silently corrupting windows.
- The demo remains one command with no external service.

## Disadvantages

- SQLite serializes writes and does not provide multi-region or multi-writer semantics.
- Feature and graph state are still in memory; only response idempotency and audit are durable.
- A crash between state mutation and the journal commit can leave process state ahead of the
  persisted record until restart.
- The five-minute bound is a configured reference policy, not evidence of a correct live SLA.

## Consequences

This improves single-process correctness but is not an exactly-once streaming claim. A
distributed implementation should atomically couple an event log offset, state mutation,
and decision record, then replay state from checkpoints. SQLite throughput must be measured
under HTTP load before any capacity statement.
