# ADR 004: Cost-optimized actions and a non-decisional challenger

- Status: Accepted
- Date: 2026-08-11

## Context

A fraud probability is not a payment action. Business costs change, and a candidate model
must be evaluated on live-path inputs without exposing customers to unproven decisions.

## Alternatives considered

1. Fixed probability threshold: simple, but hides review/customer/loss trade-offs.
2. Model emits action classes: couples training labels to mutable business policy and makes
   cost changes require retraining.
3. Separate ordered thresholds optimized on validation economics, with shadow inference for
   the challenger: explicit and reversible, but sensitive to cost assumptions and drift.

## Decision

Grid-search review and decline thresholds to minimize decomposed validation cost. Run both
versions on every event, attach challenger output to audit, and permit only champion score to
reach decisioning.

## Advantages

- Cost assumptions are inspectable and interactive.
- Risk modeling and action policy evolve independently.
- Shadow comparison includes economic outcomes, not only AUC.

## Disadvantages

- Grid search ignores uncertainty and review-capacity constraints.
- Uncalibrated/shifted scores can destabilize thresholds.
- Simulator costs are not validated business inputs.

## Consequences

Production promotion requires multi-window evidence, calibrated costs, capacity constraints,
segment checks, approval, monitoring, and rollback. Shadow superiority in one run is not a
promotion decision.

