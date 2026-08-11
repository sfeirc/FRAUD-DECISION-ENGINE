# ADR 002: Point-in-time event replay

- Status: Accepted
- Date: 2026-08-11

## Context

Fraud windows and graph statistics leak if the current event or future chargeback is visible
when its score is produced. Separate training and serving implementations commonly drift.

## Alternatives considered

1. Batch SQL feature tables: convenient for training, but easy to use non-as-of joins and
   difficult to prove equivalent to online state.
2. Separate optimized online/offline implementations: potentially faster, but doubles the
   semantic surface and requires extensive parity infrastructure.
3. Replay through shared state code: slower for research iteration, but makes ordering and
   read-before-write behavior directly testable.

## Decision

Replay chronologically through the same temporal and graph implementations as the API.
Compute first, update second; queue fraud feedback for a configurable delay.

## Advantages

- Leakage invariants are covered by unit tests.
- Feature definitions have one executable source.
- Late label availability is represented explicitly.

## Disadvantages

- Python replay is slower than vectorized batch transforms.
- Out-of-order policy is rejection rather than reconciliation.
- Equal-time ordering uses transaction ID, a simplifying convention.

## Consequences

Future warehouse pipelines must reproduce these as-of semantics. Performance optimization is
acceptable only with parity tests against replay outputs.

