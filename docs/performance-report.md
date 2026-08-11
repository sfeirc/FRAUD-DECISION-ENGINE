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

A second profile attributed 2.019 of 2.229 seconds across 50 payments to two identical
100-tree Isolation Forest calls per payment. Validation sweeps over 16/32/48/64/100 trees
selected 48: it retained the minimum configured validation cost of 1,447.44 while PR-AUC
changed from 0.6998 to 0.6995. Champion and challenger now share that fitted anomaly model and
compute its score once. A profiled 50-payment mean fell from 44.6 to 15.0 ms before the final
non-profiled benchmark measured 7.33 ms p50.

## Same-seed measurements

| Metric | Baseline | Optimized | Change |
|---|---:|---:|---:|
| Feature replay | 7.981 s | 0.139 s | 57.5× faster |
| P50 authorization latency | 36.08 ms | 7.33 ms | 79.7% lower |
| P95 authorization latency | 41.71 ms | 9.35 ms | 77.6% lower |
| P99 authorization latency | 43.92 ms | 11.94 ms | 72.8% lower |
| PR-AUC | 0.6650 | 0.7163 | +0.0513 |
| Configured estimated cost | 2,461.21 | 2,095.35 | 14.9% lower |

Both runs used seed 7, 2,225 simulator events, the same chronological partitions, cost
assumptions, Windows 11 host, Python 3.12.13, and sequential warm in-process latency scope.
The model and feature set changed intentionally. Raw rows and complete configurations remain
under `benchmarks/results/reference` and `benchmarks/results/optimized`.

## V0.3 control-plane and full-path measurements

Platt calibration and a validation review-rate constraint did not change seed-7 ranking:
PR-AUC remained 0.7163. Fraud capture moved from 84.05% to 84.60% and reviews fell from 19 to
11, but configured estimated cost rose from 2,095.35 to 2,238.39 (6.8%). This is disclosed as
a policy/control change, not a performance win.

The five-seed rerun exposed material variance: PR-AUC ranged 0.6419–0.7163 and false positives
ranged 2–60. This is why the repository no longer leads with only the best seed.

The new loopback HTTP suite includes durable SQLite writes. With 500 measured requests per
level, throughput was 70.1/91.9/90.9/82.6 req/s at concurrency 1/4/8/16 and client p99 was
23.44/63.25/147.98/295.34 ms, with zero request errors. The plateau after concurrency 4 is
consistent with serialization around state mutation; no optimization claim is made without
changing and remeasuring that boundary.

## Trade-offs and non-claims

False positives increased from 5 to 20 and reviews from 5 to 19 while recall and fraud amount
capture increased. The lower configured cost follows the documented cost assumptions; a
business with different customer-friction costs can produce a different optimum.

The HTTP benchmark establishes only a local baseline, not remote capacity or a production
SLO. SQLite makes response/audit records durable, while feature and graph state still require
transactional recovery or reconstruction from an event log. The component index duplicates
NetworkX state; tests cover reference transitions, not arbitrary crash recovery.
