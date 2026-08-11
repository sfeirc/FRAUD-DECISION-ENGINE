# Benchmark methodology

## Commands and artifacts

```bash
make benchmark       # seed-7 quality + sequential in-process latency
make robustness      # five independently trained/evaluated seeds
make load-benchmark  # real HTTP server at concurrency 1/4/8/16
```

Every suite writes JSON containing hardware, OS, software, commit, and full configuration;
CSV containing raw measurements; and SVG generated automatically from saved results.

| Suite | Raw data | Summary | Figure |
|---|---|---|---|
| Seed 7 | `v0.3/raw_measurements.csv` | `v0.3/summary.json` | quality + latency SVG |
| Five seed | `robustness/per_seed.csv` | `robustness/summary.json` | robustness SVG |
| HTTP load | `http-load/raw_requests.csv` | `http-load/summary.json` | concurrency SVG |

## Quality protocol

Events are ordered by event time and transaction ID. Features use a two-hour simulated label
confirmation delay and split chronologically into 65% train, 15% validation, and 20% test.
Models fit only on train. Platt calibration and champion thresholds fit on validation. Test is
evaluated once with frozen models and policy.

The five-seed run repeats the entire generation/fit/calibration/policy/test process for seeds
7, 19, 31, 43, and 59. Its 95% interval is the 2.5/97.5 percentile of 10,000 deterministic
non-parametric bootstrap resamples of the five seed results. It quantifies variation inside
this simulator, not external population uncertainty.

## Economic accounting

The minimized cost is unrecovered fraud loss + legitimate false-positive cost + manual review
cost + per-authorization operational cost. Reviews capture a configurable fraction of fraud
and have lower customer-friction cost than declines. Validation candidates above the maximum
review rate are rejected.

“Estimated fraud prevented” means declined amount carrying a simulator fraud label. It is a
controlled comparison metric, not forecast or realized saving.

## Latency and HTTP protocol

The seed-7 benchmark calls `FraudDecisionService.authorize` sequentially. It includes
feature/graph work, both models, champion contributions, response construction, and the
in-memory benchmark journal; it excludes HTTP/network.

The HTTP suite starts a fresh one-worker Uvicorn process and fresh SQLite file per concurrency
level. After 25 excluded warmups, an async pooled HTTP/1.1 client sends 500 measured requests.
It includes request parsing/validation, scheduling, temporal/graph mutation, both models,
explanation, response serialization, and SQLite WAL/full-sync write. Client and server share
the same host over loopback; TLS, proxy, containers, remote network, failures, and sustained
soak are excluded.

## Interpretation rules

- PR-AUC is the primary ranking metric; ROC-AUC is reference context.
- Fixed-FPR recall links fraud capture to customer-friction budget.
- Brier/ECE test probability behavior but do not validate simulated calibration in production.
- Cost moves with explicit assumptions and must be reported alongside false positives/reviews.
- Latency and throughput belong only to the recorded host/protocol/configuration.
- No benchmark here supports a production scale, SLO, or realized financial claim.
