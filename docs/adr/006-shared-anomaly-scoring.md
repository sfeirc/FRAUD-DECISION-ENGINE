# ADR 006: Shared, validation-sized anomaly scoring

- Status: Accepted
- Date: 2026-08-11

## Context

Profiling attributed 91% of the online path to Isolation Forest. Champion and challenger had
identical fitted anomaly models but evaluated both, while each forest contained 100 trees.

## Alternatives considered

1. Remove anomaly detection: fastest, but discards a complementary unlabeled risk signal.
2. Cache scores by entity: invalid because the feature vector changes with every event.
3. Batch online requests: efficient at load, but introduces queueing delay and does not help
   isolated authorizations.
4. Share the identical anomaly model/score and select tree count on validation evidence:
   preserves the signal with less repeated work, but couples shadow models to one anomaly
   definition.

## Decision

Fit a 48-tree Isolation Forest on legitimate training rows, share that fitted object between
champion and challenger, and calculate its score once per authorization. If models do not
share the same object, the service falls back to independent scoring.

## Evidence

Validation sweeps produced:

| Trees | Validation PR-AUC | Estimated cost |
|---:|---:|---:|
| 16 | 0.6995 | 1,507.44 |
| 32 | 0.6994 | 1,504.84 |
| 48 | 0.6995 | 1,447.44 |
| 64 | 0.6981 | 1,447.44 |
| 100 | 0.6998 | 1,447.44 |

The smallest forest retaining the minimum cost was 48 trees. On the frozen test benchmark it
measured PR-AUC 0.7163 and 13.22 ms p99, versus baseline 0.6650 and 43.92 ms p99.

## Advantages

- Removes a duplicate shadow-path computation.
- Retains anomaly contribution in both risk fusions.
- Makes fallback semantics explicit when anomaly models differ.

## Disadvantages

- Challenger cannot independently experiment with anomaly-model structure while sharing.
- Validation results are synthetic and do not establish the same tree count for live data.
- Isolation Forest remains the largest measured online component.

## Consequences

An anomaly-model challenger must use an independent fitted object, accepting the measured
latency cost. Promotion experiments must report both quality and online-path latency.

