# Known limitations

## Data and measurement

- All identities, labels, fraud losses, and customer-friction costs are simulated.
- The checked benchmark is one deterministic seed and one workstation; no uncertainty band
  or cross-population validity is claimed.
- Simulator behavior is documented but cannot represent real authorization selection bias,
  chargeback delay, adversarial adaptation, or regional regulation.
- Scores are not probability-calibrated. Cost optimization uses their rank and empirical
  validation outcomes.

## Runtime

- Temporal state, graph, audit log, and model objects are process-local and non-durable.
- The service lock provides deterministic local mutation, not horizontal consistency.
- No event broker, idempotency store, replay checkpoint, late-event reconciliation, hot-key
  protection, backpressure, or disaster recovery exists.
- The measured latency excludes HTTP/network transport, concurrency, cold start, and durable
  storage. No throughput or scale claim is made.

## Operations and governance

- There is no authentication/authorization, secret management, encryption policy, PII
  tokenization, data retention enforcement, or regulatory control mapping.
- The review queue is a dashboard view, not a case-management workflow.
- Shadow metrics are calculated, but automated promotion, rollback, drift alerts, and model
  registry integration are not implemented.
- Explanations are model contribution values and rules; they have not been validated with
  investigators or for adverse-action requirements.

## Modeling

- Categorical event fields enter models indirectly through behavioral features rather than
  a full encoding strategy.
- Confirmed-fraud graph feedback uses a fixed simulated delay.
- The graph is unbounded in memory and component traversal is unsuitable for large graphs.
- No graph ML model is included because no measured incremental value has been demonstrated.

