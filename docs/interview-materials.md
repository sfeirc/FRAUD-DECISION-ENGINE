# Recruiter and interview materials

## Technical talking points

- Start with read-before-write: temporal and graph features exclude the current payment, and
  confirmed fraud arrives only after a delay.
- Separate ranking, calibration, and action: XGBoost/anomaly/graph estimate risk; Platt scaling
  gives testable probability behavior; economic thresholds own the customer decision.
- Explain why a validation queue cap is not a runtime guarantee: two unseen seeds exceeded 5%,
  motivating a hard time-bucketed capacity controller.
- Defend the GNN omission: structural signals are inspectable and no incremental experiment
  justifies learned message-passing cost.
- Describe the durability boundary precisely: SQLite makes exact retries and audit durable;
  temporal/graph state is still in memory, so this is not exactly-once streaming.
- Use the load curve to explain architecture: throughput peaked around concurrency 4 and p99
  climbed at 8/16 because ordered state mutation is serialized.
- Discuss the adverse result: v0.3 gained control/calibration but seed-7 configured cost rose
  6.8%. Engineering credibility means publishing that, not renaming it an optimization.

## Three CV bullets

- Built an auditable payment fraud decision engine combining leakage-safe velocity features,
  XGBoost, Isolation Forest, Platt calibration, and an indexed customer/card/device/IP/merchant
  graph to produce cost-sensitive approve/review/decline actions.
- Implemented checksum-verified champion/challenger artifacts, shadow inference, TreeSHAP-style
  explanations, SQLite-backed idempotent retries/audit, late-event watermarks, Prometheus
  metrics, and a one-command coordinated-ring dashboard demo.
- Created reproducible seed-7, five-seed, and real-HTTP benchmark suites with raw data and
  environment capture; measured 0.6677 mean PR-AUC across five synthetic seeds and local
  single-worker saturation near concurrency 4 (explicitly scoped, not a production claim).

## LinkedIn project description

I built Aegis, an end-to-end payment fraud decision engine focused on what classification
demos usually omit: point-in-time state, coordinated entity risk, calibrated probabilities,
economically explicit approve/review/decline policy, retry correctness, model provenance, and
operational evidence. The service combines XGBoost, Isolation Forest, and an incremental
customer/card/device/IP/merchant graph; runs a challenger in shadow; and returns model
contributions, rules, graph signals, trace IDs, and latency. Its demo injects a coordinated
shared-device/IP ring and exposes cost and review-capacity controls in a live dashboard. I
published raw single-seed, five-seed, and concurrent HTTP results—including regressions and
variance—plus CI, tests, ten ADRs, limitations, and a technical report. All metrics come from
checked synthetic runs and are labeled as such.

## 30-second interview pitch

Aegis is a payment fraud decision system, not a Kaggle classifier. It computes leakage-safe
temporal and graph features, fuses supervised and anomaly risk, calibrates the score, then
uses explicit fraud, customer, and review costs to approve, review, or decline. A challenger
runs in shadow and each response is explainable, versioned, idempotent, and journaled. The
demo makes a coordinated ring visible. I also measured five independent seeds and the real
HTTP path; the results expose both quality variance and the single-process contention limit,
so the repository shows engineering judgment rather than unsupported scale claims.

## Two-minute technical interview pitch

The core invariant is point-in-time correctness. For each authorization, Aegis checks the
idempotency journal and customer watermark, then reads temporal windows and graph structure
before inserting the event. Offline training replays through the same feature and graph code,
and simulated fraud labels enter neighborhood statistics only after a confirmation delay.

The risk layer is deliberately complementary. XGBoost learns labeled interactions, Isolation
Forest scores novelty against legitimate training traffic, and the graph captures shared
devices/IPs, component size, degree, merchant concentration, and delayed neighbor fraud. An
incremental union-find index avoids traversing the whole connected component per request. A
Platt calibrator is fitted on chronological validation. The score still does not directly
block a payment: ordered review/decline thresholds minimize configured fraud loss, customer
harm, analyst cost, and operating cost while respecting a validation review-rate constraint.

Champion and challenger are bundled with their feature order, calibration, policy,
dependencies, source commit, and SHA-256 checksum. Startup loads that artifact rather than
retraining. Every decision includes champion and shadow scores, native XGBoost contribution
values, rules, graph signals, model version, timestamp, trace ID, and latency. SQLite provides
exact retry semantics, request-hash conflicts, customer watermarks, and durable audit, but I
am careful not to call in-memory feature/graph state exactly once.

The evidence has three layers. Seed 7 measured 0.7163 PR-AUC and 84.60% fraud-value capture
on 445 synthetic test payments. Across five separately trained seeds, mean PR-AUC was 0.6677
and false positives ranged from 2 to 60—important variance hidden by one seed. A 2,000-request
loopback HTTP run with full-sync SQLite measured about 92 req/s at concurrency 4, then
saturated; p99 rose from 23 ms at concurrency 1 to 295 ms at 16. Those are local reference
measurements, not live accuracy or a production SLO. The next step is event-log-backed state
recovery and a hard runtime review budget, followed by failure-injected distributed tests.

## Recruiter 30-second test

- **What is impressive?** A complete, measurable fraud decision path: leakage control, graph
  intelligence, calibrated economic policy, shadowing, provenance, retry correctness, and
  full-path load evidence.
- **Can it be reproduced?** Yes: `make demo`, `make benchmark`, `make robustness`, and
  `make load-benchmark` save raw data, environment, configuration, and generated figures.
- **Are claims measurable?** Yes, and scopes/adverse outcomes are adjacent to each number.
- **Are important internals implemented here?** Yes: simulator, online features, graph index,
  fusion, policy optimizer, artifact contract, idempotency journal, and benchmark harness.
- **Can decisions be defended?** Ten ADRs record alternatives, advantages, disadvantages, and
  consequences; limitations distinguish implemented controls from distributed successors.
