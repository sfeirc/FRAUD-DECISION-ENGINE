# Recruiter and interview materials

## Technical talking points

- The hard boundary is read-before-write state: explain how both temporal and graph features
  exclude the current payment and how fraud feedback is delayed.
- Separate risk ranking from action policy: the model estimates risk; validation-time cost
  optimization selects approve/review/decline thresholds.
- Explain why the challenger can have slightly higher fraud capture yet higher total cost,
  and why one synthetic window is insufficient for promotion.
- Defend the absence of a GNN: structural signals are inspectable and no benchmark has yet
  justified added serving complexity.
- Be explicit that p99 is sequential in-process latency, not an HTTP SLO or throughput test.

## Three CV bullets

- Built a real-time payment authorization reference that fuses XGBoost, Isolation Forest,
  point-in-time velocity features, and an incremental customer/card/device/IP/merchant graph
  into auditable approve/review/decline decisions.
- Implemented leakage-safe offline replay, delayed fraud feedback, native TreeSHAP reason
  factors, and non-decisional champion/challenger shadow scoring behind a FastAPI contract.
- Created a reproducible economic/latency benchmark with raw measurements and environment
  capture; on its documented synthetic holdout, measured 0.7179 PR-AUC and 27.04 ms in-process
  p99 latency (single host, sequential requests, excluding HTTP transport).

## LinkedIn project description

I built Aegis, an end-to-end fraud decision engine focused on the part a classification demo
usually omits: turning uncertain risk into an economically explicit approve, review, or
decline action. The service combines leakage-safe temporal features, XGBoost, Isolation
Forest, and an incremental entity graph; runs a challenger in shadow mode; and returns model
versions, native contribution factors, rules, graph signals, trace IDs, and latency for every
authorization. A deterministic demo injects a coordinated shared-device/IP ring and lets the
operator change customer-friction costs to re-optimize thresholds. The repository includes
tests, CI, ADRs, raw benchmark rows, generated figures, and prominent limitations. All
published numbers are from the checked synthetic benchmark and are labeled accordingly.

## 30-second interview pitch

Aegis is a payment fraud decision engine, not just a classifier. A payment is scored using
point-in-time velocity features, XGBoost, Isolation Forest, and graph signals across customer,
card, device, IP, and merchant. A separate cost engine chooses approve, review, or decline,
while a challenger runs in shadow and every response is explainable and auditable. The demo
injects a coordinated ring and visibly changes graph risk and decisions. I also built a
reproducible benchmark that records every raw result and its exact environment, and I state
clearly where the in-memory reference stops short of production infrastructure.

## Two-minute technical interview pitch

The design starts with a strict point-in-time contract. For each authorization, the service
reads customer windows and graph structure before inserting the payment. Offline training
replays through that exact code, and simulated fraud confirmations enter graph statistics
only after a delay. That prevents the two most common leakage paths in fraud projects.

The risk layer is deliberately complementary. XGBoost learns labeled interactions, Isolation
Forest provides a novelty view trained on legitimate traffic, and the graph captures shared
devices, IPs, suspicious components, degree, merchant concentration, and neighborhood fraud.
Their fused score does not directly block a payment. I grid-search ordered review and decline
thresholds using explicit fraud-loss, customer-friction, analyst, and operating costs on a
chronological validation window. A second model scores the identical event in shadow but
cannot influence the customer decision.

Every result includes the champion version, shadow result, native XGBoost contribution
values, deterministic rules, graph signals, timestamp, trace ID, and measured latency. The
dashboard streams those decisions, renders a detected ring, and re-optimizes thresholds when
cost assumptions change.

For evidence, the checked synthetic benchmark saves 445 raw held-out rows plus hardware,
OS, dependencies, commit, configuration, and generated SVGs. It measured 0.7179 PR-AUC and
27.04 ms in-process p99 on one sequential Windows host. I would not call that a production
SLO: state is local and non-durable, latency excludes transport and concurrency, and labels
are synthetic. The next engineering step is an idempotent event-log-backed state layer, then
multi-window promotion gates and concurrent failure testing.
