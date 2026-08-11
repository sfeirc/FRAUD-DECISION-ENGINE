# Benchmark methodology

## Reproduction

```bash
python -m fraud_engine.benchmark \
  --normal-events 2000 --seed 7 \
  --output-dir benchmarks/results/reference

python -m fraud_engine.compare \
  benchmarks/results/reference/summary.json \
  benchmarks/results/optimized/summary.json
```

The command saves:

- `summary.json`: CPU/OS, package versions, commit, all configuration, costs, thresholds,
  partitions, quality/business metrics, and latency percentiles;
- `raw_measurements.csv`: one row per held-out payment with label, attack family, amount,
  both scores, champion decision, and measured online-path latency;
- `quality_metrics.svg` and `latency.svg`: generated directly from the saved measurements.

The comparison command writes a machine-readable delta report and an SVG that includes
quality, latency, cost, capture, and the false-positive trade-off.

## Protocol

Events are ordered by event time and transaction ID. Features are generated with a two-hour
confirmation delay, then split chronologically into 65% train, 15% validation, and 20% test.
Models fit only on train. Champion cost thresholds fit only on validation. Both model versions
are evaluated with those frozen thresholds on test.

Latency uses sequential, warm, in-process calls to `FraudDecisionService.authorize`. It
includes temporal and graph state, champion and challenger inference, native XGBoost
contributions, explanations, and audit serialization. It excludes HTTP parsing, network,
containers, load balancing, cold start, concurrency, and durable storage.

## Economic accounting

The minimized cost is the sum of:

```text
unrecovered fraud loss
+ legitimate-customer false-positive cost
+ manual-review cost
+ per-authorization operational cost
```

Reviews capture a configurable fraction of fraudulent value and impose both review cost and
lower legitimate-customer friction. Declines prevent simulated fraud value but charge the
full false-positive cost on legitimate payments.

The reported “estimated fraud prevented” is declined amount with a simulator fraud label.
It is useful for comparing configurations inside this controlled experiment; it is not a
forecast or realized saving.

## Interpretation

One seed and one machine do not produce a confidence interval. PR-AUC is primary because the
positive class is rare; ROC-AUC is reference context. Fixed-FPR recall connects the score to
a customer-friction budget. Economic results depend directly on stated cost assumptions.
