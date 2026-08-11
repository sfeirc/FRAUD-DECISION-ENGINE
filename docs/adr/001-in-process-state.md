# ADR 001: In-process state for the reproducible reference

- Status: Accepted
- Date: 2026-08-11

## Context

Temporal and graph features require mutable online state. A reference implementation must be
executable without external setup while remaining honest about distributed guarantees.

## Alternatives considered

1. Kafka + Flink + Redis/Feast: realistic topology, but substantial operational machinery
   would obscure state semantics and could not be validated here as a production deployment.
2. Redis-only atomic updates: easier persistence, but event-time windows and graph traversal
   still need ordering, replay, and multi-key consistency design.
3. Process-local state with serialized mutation: deterministic and zero-configuration, but
   non-durable and not horizontally scalable.

## Decision

Use in-memory temporal/graph state and serialize authorization mutation per process.

## Advantages

- One-command demo and reproducible transition tests.
- Online and offline paths share the same small, inspectable implementation.
- No unsupported throughput, exactly-once, or scale claim.

## Disadvantages

- Restart loses state and audit history.
- Multiple replicas would diverge.
- Graph growth and the duplicated component index are unbounded and non-durable.

## Consequences

The repository is a reference system, not production-ready. A distributed version must
define idempotency keys, partition ownership, late-event policy, checkpoint/replay behavior,
durable audit, and online/offline consistency tests before scale testing.
