# Technical report: risk decisions, not classifications

## Executive summary

Aegis is an executable reference for the full fraud decision loop: event simulation,
point-in-time state, complementary risk signals, cost-based actions, explanations, audit,
shadow evaluation, dashboarding, and reproducible measurement. It deliberately does not
claim production scale or live financial impact.

## Why fraud imbalance changes evaluation

If fraud prevalence is 0.2%, an always-legitimate classifier is 99.8% accurate and prevents
nothing. Even ROC-AUC can conceal operational pain because it averages behavior over false-
positive regions a payment team would never tolerate. PR-AUC focuses on positive-class
retrieval; precision estimates review/decline purity, while recall estimates missed fraud.
Recall at a fixed false-positive rate makes the customer-friction budget explicit.

Transaction value matters too. Missing a €2 card test and a €2,000 takeover counts equally
in ordinary recall but not in loss. The report therefore adds fraud amount captured, false
positives, reviews, and decomposed estimated cost.

## Precision, recall, and customer harm

Lowering thresholds usually captures more fraud but blocks more legitimate customers. That
harm includes abandoned purchases, support contacts, merchant dissatisfaction, and lost
trust—not only the immediate order value. Reviews offer a middle action but consume analyst
capacity and add delay. The decision layer keeps these trade-offs outside the model so risk
estimation and business policy can evolve independently.

## Cost-sensitive decisions

Two ordered thresholds map fused risk into approve, review, or decline. Grid search minimizes
unrecovered fraud, false-positive impact, review expense, and operating expense over the
validation period. The dashboard re-runs that optimization when assumptions change. A real
deployment should add review-capacity constraints, score calibration, confidence intervals,
and segment-specific policies rather than treating these simulator costs as universal.

## Online/offline consistency and leakage

Stateful fraud features are particularly vulnerable to future information. A feature such as
“transactions in the last hour” is invalid if the current event is inserted before the
window is read. Neighborhood fraud rate is invalid if a future chargeback is attached at
authorization time. Aegis uses read-before-write state and delayed label feedback, and the
offline builder calls the same implementations as online authorization.

## Graph intelligence

Fraudsters rotate individual accounts while reusing infrastructure. The heterogeneous graph
links customer, card, device, IP, and merchant. Shared device/IP counts reveal fan-out;
connected-component size and degree reveal coordination; delayed confirmed-fraud density
propagates known risk; merchant concentration catches common compromise points. The graph
view also gives investigators a compact explanation that a scalar model score cannot.

No graph neural network is included. The reference dataset and single-seed benchmark do not
show that learned message passing improves cost enough to justify training, serving, and
explanation complexity. That is an experiment to earn, not a résumé feature to assume.

## Champion/challenger operation

Both versions score every payment from the same features. The champion alone enters the
decision engine; challenger output is attached to the audit record and compared economically
under champion thresholds. Promotion would require several time windows, uncertainty tests,
segment analysis, drift checks, and an explicit rollback plan. This repository implements
shadow execution, not automatic promotion.

## Concept drift

Fraud tactics, merchant mix, authentication policy, customer travel, and seasonal spend all
move feature and label distributions. Monitoring should cover input drift, score calibration,
action rate, delayed precision/recall, fraud amount capture, review yield, segment fairness,
and latency. Retraining on a fixed cadence alone is insufficient because labels are delayed
and attackers adapt to interventions.

## Reference findings

The optimized reference run achieved champion PR-AUC 0.7163 and recall 0.7368 on 445 held-out
synthetic events. At validation-optimized thresholds, it captured 84.05% of labeled fraud
amount with 20 false positives and 19 reviews. The shadow challenger captured the same amount
but had higher estimated total cost (2,233.93 versus 2,095.35), so this single experiment
supplies no case for promotion. Full context is in the optimized `summary.json`.

Against the preserved same-seed baseline, component-indexing and shadow explanation changes
reduced feature replay from 7.981 to 0.139 seconds and p99 in-process authorization latency
from 43.92 to 11.94 ms. Added authorization-time features and validation-selected fusion
raised PR-AUC from 0.6650 to 0.7163 and reduced configured estimated cost by 14.9%. False
positives rose from five to 20, an explicit business trade-off rather than a universal win.

## What the evidence does not establish

It does not establish production accuracy, calibrated probabilities, concurrent capacity,
durability, exactly-once processing, fairness, regulatory compliance, or a latency SLO. The
synthetic generator is useful for controlled failure modes but cannot reproduce an issuer's
selection effects, feedback loops, fraud-label delay, or adversarial adaptation.
