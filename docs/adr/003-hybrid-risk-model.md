# ADR 003: Hybrid risk model without graph deep learning

- Status: Accepted
- Date: 2026-08-11

## Context

Supervised models exploit confirmed patterns, anomaly detection covers novelty, and graphs
expose coordinated infrastructure. The project needs complementary signals without adding
unmeasured complexity.

## Alternatives considered

1. XGBoost alone: strong tabular baseline, but no independent novelty or explicit graph view.
2. Graph neural network: can learn neighborhood representations, but needs temporal graph
   sampling, serving infrastructure, calibration, and evidence of incremental economic value.
3. XGBoost + Isolation Forest + explicit graph signals: interpretable components and modest
   serving requirements, with native contribution values for the supervised part.

## Decision

Fuse XGBoost, Isolation Forest, and deterministic graph risk with versioned weights.

## Advantages

- Each signal can be inspected and ablated.
- Graph rings remain human-readable.
- Native XGBoost contribution values avoid an additional explanation dependency.

## Disadvantages

- Fusion weights are configured, not learned/calibrated end to end.
- Isolation score transformation is heuristic.
- Hand-designed graph features may miss subtle topology.

## Consequences

A GNN should be proposed only after a temporal, cost-based ablation demonstrates material
improvement and its latency/operational cost is measured.

