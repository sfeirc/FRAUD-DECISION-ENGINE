# ADR 008: Calibrate risk and constrain review capacity

- Status: accepted
- Date: 2026-08-11

## Context

The fused v0.2 score ranked transactions, but it was not probability-calibrated. The cost
optimizer also treated manual review as infinitely available: it charged each review but did
not prevent a threshold pair from exceeding the operating team's queue capacity.

## Alternatives considered

1. Treat the fused score as a probability and rely only on review cost. This is simple but
   gives the score stronger semantics than the evidence supports.
2. Use isotonic regression. It is flexible but can overfit the small chronological validation
   partition and introduces stepwise ties.
3. Use Platt scaling plus an explicit maximum review rate during threshold search.

## Decision

Use option 3. Each model fits a one-dimensional logistic calibrator on its chronological
validation scores. The held-out test partition remains untouched. Threshold optimization
rejects candidates whose validation review rate exceeds the configured capacity (5% by
default). Brier score, expected calibration error, and observed review rate are reported.

## Advantages

- Scores have empirically testable probability behavior through calibration metrics.
- Economic optimization cannot silently propose an infeasible review queue.
- Capacity and cost assumptions remain interactive and visible in benchmark metadata.

## Disadvantages

- A calibration model estimated from simulated data does not transfer validity to live data.
- A rate constraint is a simplified capacity model; it does not model hourly staffing or
  priority queues.
- Threshold selection and calibration share the validation partition, which can overfit
  policy selection even though final reporting remains held out.

## Consequences

Calibration quality must be monitored separately from ranking quality. A real deployment
should use larger rolling calibration windows, segment-level diagnostics, and an absolute
time-varying review budget. The multi-seed benchmark quantifies simulator-seed sensitivity,
not uncertainty on real payment populations.
