# Performance engineering report

## Bottleneck evidence

A cProfile run over 1,108 deterministic events attributed 4.329 of 4.381 seconds to graph
feature computation. NetworkX connected-component queries accounted for 3.554 seconds and
the replay executed 15.56 million calls. The graph had become highly connected through
merchants, so every authorization repeatedly traversed much of the same component.

## Selected optimization

The runtime graph still stores explicit NetworkX nodes/edges for ring visualization. A
separate disjoint-set index now maintains component parent, size, observation count, and
confirmed-fraud count. Candidate-payment features combine the unique roots touched by its
customer/card/device/IP/merchant nodes before the event is inserted.

Union-by-size and path compression make component lookup near-constant amortized time. Fraud
confirmation increments the current component aggregate, preserving delayed feedback.
Equivalence tests compare indexed component size with a direct NetworkX traversal before
mutation.

The shadow challenger also stopped calculating TreeSHAP contributions that were never
returned. Champion explanations remain present on every authorization. Offline threshold and
benchmark evaluation now score matrices in batches instead of making one model call per row.

## Same-seed measurements

| Metric | Baseline | Optimized | Change |
|---|---:|---:|---:|
| Feature replay | 7.981 s | 0.100 s | 79.5× faster |
| P50 authorization latency | 36.08 ms | 18.43 ms | 48.9% lower |
| P95 authorization latency | 41.71 ms | 21.81 ms | 47.7% lower |
| P99 authorization latency | 43.92 ms | 27.04 ms | 38.4% lower |
| PR-AUC | 0.6650 | 0.7179 | +0.0529 |
| Configured estimated cost | 2,461.21 | 2,095.35 | 14.9% lower |

Both runs used seed 7, 2,225 simulator events, the same chronological partitions, cost
assumptions, Windows 11 host, Python 3.12.13, and sequential warm in-process latency scope.
The model and feature set changed intentionally. Raw rows and complete configurations remain
under `benchmarks/results/reference` and `benchmarks/results/optimized`.

## Trade-offs and non-claims

False positives increased from 5 to 20 and reviews from 5 to 19 while recall and fraud amount
capture increased. The lower configured cost follows the documented cost assumptions; a
business with different customer-friction costs can produce a different optimum.

No throughput, concurrent latency, distributed graph, durability, or production SLO claim is
made. The component index adds duplicated state that must remain consistent with NetworkX;
tests cover the reference transitions, but a durable implementation would need transactional
recovery or reconstruction from the event log.

