# Technical report: fraud decisions, not classifications

## Executive summary

Aegis is an executable reference for payment authorization: point-in-time event state,
supervised/anomaly/graph risk, calibrated scores, economic action policy, shadow evaluation,
explanation, idempotency, durable audit, and reproducible measurement. It does not claim live
fraud performance, distributed correctness, or production readiness.

## Why class imbalance changes the problem

At 0.2% fraud prevalence, an always-legitimate classifier is 99.8% accurate and prevents no
loss. ROC-AUC can also conceal operational pain because it averages false-positive regions a
payment team would never accept. PR-AUC focuses on positive retrieval; precision represents
review/decline purity; recall represents missed fraud; recall at fixed FPR makes a
customer-friction budget explicit.

Value matters. Missing a €2 card test and a €2,000 takeover counts equally in ordinary recall
but not economically. Aegis therefore reports captured fraud amount, false positives, review
volume, calibrated probability error, decomposed cost, and tail latency. Accuracy is omitted
from the recruiter-facing result table by design.

## Precision, recall, and customer harm

Lowering a threshold generally captures more fraud while blocking more legitimate customers.
That harm includes abandoned purchases, support contacts, merchant dissatisfaction, and lost
trust—not only order value. Review offers a middle action but consumes investigators and adds
delay. The risk model and policy are separate so ranking can change without silently changing
business action.

Two ordered thresholds map risk into approve, review, or decline. Validation search minimizes:

```text
unrecovered fraud loss
+ legitimate-customer false-positive cost
+ manual-review cost
+ per-authorization operating cost
```

Candidates above a configured validation review-rate cap are rejected. The five-seed test
showed that this soft planning constraint can still exceed 5% out of sample; a real system
needs a hard time-bucketed queue controller and service-level monitoring.

## Calibration and policy selection

The raw fused score is not assumed to be a probability. Each model fits deterministic Platt
scaling on its chronological validation scores. Brier score and expected calibration error
are then measured on test. Calibration preserves ranking order, so PR-AUC/ROC-AUC should not
improve merely from this step.

Calibration and threshold selection currently share validation data. The test partition is
untouched, but the policy can still overfit validation. A larger system should use separate
calibration/policy periods or nested rolling evaluation, with segment-level calibration and
delayed-outcome correction.

## Online/offline consistency and leakage

Stateful fraud features are vulnerable to future information. “Transactions in the last
hour” leaks if the current event is inserted before the window is read. Neighborhood fraud
rate leaks if an eventual chargeback is attached at authorization. Aegis uses read-before-
write state and delayed feedback; offline replay calls the same implementations as online.
Tests assert window boundaries, first-use behavior, and delayed graph labels.

Events more than five minutes behind a customer's persisted watermark are rejected rather
than silently applied to forward-only state. This is a documented reference policy, not a
claim that five minutes is universally correct.

## Graph intelligence

Fraudsters rotate accounts while reusing infrastructure. The heterogeneous graph links
customer, card, device, IP, and merchant. Shared device/IP counts reveal fan-out; component
size and degree reveal coordination; delayed confirmed-fraud density propagates known risk;
merchant concentration catches common compromise points.

An incremental union-find index stores component aggregates for scoring; NetworkX retains
explicit edges for investigator visualization. This avoids a full connected-component walk
per payment. No GNN is included because no experiment demonstrates enough incremental
economic value to justify training, serving, and explanation complexity.

## Champion/challenger and artifacts

Champion and challenger score identical features. Only champion risk enters policy; the
challenger result is journaled and compared under champion thresholds. The fitted estimators,
calibrators, validation records, thresholds, assumptions, feature order, source commit, and
dependency versions are stored in a versioned bundle. Startup validates its SHA-256 checksum
and feature contract and never retrains.

This is a local artifact contract, not a model registry. Promotion still needs several time
windows, economic confidence bounds, calibration/segment analysis, drift checks, human
approval, and rollback.

## Retry, ordering, and audit semantics

Transaction ID is the idempotency key. SQLite stores a hash of the complete request and the
complete response under WAL and full synchronous writes. An exact retry returns the original
response without updating features or graph state; a different payload under the same ID is
rejected. The audit API reads the durable journal.

Feature and graph state remain in memory. Therefore this is not an exactly-once stream: a
crash between state mutation and journal commit can create an inconsistency, and state is not
reconstructed after restart. A distributed design must atomically couple event-log offset,
state update, and decision record, or make replay the source of truth.

## Concept drift and customer impact

Fraud tactics, merchant mix, authentication policy, travel, and seasonality move input and
label distributions. Monitoring should cover input/score drift, calibration, action rate,
queue utilization, delayed precision/recall, amount capture, review yield, segment parity,
and latency. Retraining on a fixed cadence is insufficient because labels are delayed and
interventions change what becomes observable.

False positives deserve the same governance as loss. Thresholds should be segmented only
when sample size, compliance review, and fairness evidence support the added complexity.
Approval-rate or revenue guardrails must not become hidden substitutes for protected-class
analysis.

## Measured findings

The seed-7 held-out result measured 0.7163 PR-AUC, 0.7368 recall, 0.5526 recall at 1% FPR,
0.0455 Brier score, 84.60% fraud-value capture, 20 false positives, and 11 reviews on 445
synthetic test events. Calibrated v0.3 estimated cost was 2,238.39, 6.8% higher than the v0.2
seed-7 policy despite slightly higher capture; calibration/capacity is not presented as a cost
optimization.

Across five independent seeds, mean PR-AUC was 0.6677 (bootstrap interval 0.6501–0.6937),
fraud capture was 84.61% (82.39%–86.62%), and false positives ranged from 2 to 60. This wider
result replaces the temptation to treat the best seed as typical.

The full-path load benchmark measured zero errors over 2,000 requests. Throughput rose from
70.1 req/s at concurrency 1 to 91.9 req/s at concurrency 4, then saturated; p99 client latency
rose from 23.44 ms to 295.34 ms by concurrency 16. The shared lock is the demonstrated local
contention boundary.

## What the evidence does not establish

The evidence does not establish live precision, realized savings, probability calibration on
real customers, fairness, remote/TLS latency, sustained capacity, distributed graph
consistency, state recovery, regulatory compliance, or an SLO. The simulator is useful for
controlled attack patterns but cannot reproduce issuer selection effects, adaptive attackers,
chargeback censoring, or regional policy.
