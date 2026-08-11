# Known limitations

## Data and measurement

- All identities, labels, losses, and customer-friction costs are simulated.
- Five seeds quantify simulator-seed sensitivity, not confidence on a live payment population.
- The simulator does not reproduce authorization selection bias, chargeback censoring,
  adversarial adaptation, regional regulation, or feedback from past interventions.
- Calibration and threshold selection share validation; final test remains held out, but
  policy-selection uncertainty can be underestimated.
- HTTP load uses one workstation, loopback, one Uvicorn worker, and 500 requests per level.
  It excludes TLS, proxy, container, remote network, failures, and sustained soak behavior.

## Runtime and state

- Temporal and graph state are process-local, unbounded, and not reconstructed after restart.
- The SQLite journal makes retries/audit durable, not feature/graph mutation exactly once.
- A crash between in-memory mutation and journal commit can leave state ahead of persistence.
- SQLite is a single-writer reference choice; no horizontal consistency is claimed.
- A global lock guarantees local read-before-write order and causes measured saturation near
  concurrency 4 on the checked host.
- Late events beyond five minutes are rejected; there is no correction/retraction workflow.
- The union-find component index cannot delete edges or split components.

## Decision policy

- The review-rate limit constrains validation threshold search; it is not a hard runtime queue
  quota. Two of five unseen seeds exceeded the 5% target.
- Costs are configurable assumptions, not measured customer lifetime value or investigator
  economics.
- No segment-specific threshold, fairness constraint, absolute staffing schedule, or queue
  prioritization policy is implemented.

## Operations and governance

- There is no API authentication/authorization, encryption policy, PII tokenization, key
  management, retention enforcement, or regulatory control mapping.
- The dashboard review count is not a case-management workflow.
- Prometheus-format metrics exist, but there is no collector configuration, alert rule,
  tracing backend, drift alert, or on-call runbook.
- Artifact checksums detect accidental modification; they are not signatures or a registry
  approval workflow.
- Shadow metrics exist, but promotion and rollback are not automated.
- Explanations have not been validated with investigators or adverse-action requirements.

## Modeling

- Categorical fields enter indirectly through behavioral features rather than a full encoding
  strategy.
- Confirmed graph feedback uses a fixed simulated delay.
- Platt scaling on simulated validation data does not establish live calibration.
- No graph ML model is included because no measured incremental value justifies it.
