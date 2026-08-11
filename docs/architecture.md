# Architecture

## Runtime path

```mermaid
sequenceDiagram
    participant C as Payment client
    participant A as Authorization API
    participant F as Temporal state
    participant G as Entity graph
    participant M as Champion + challenger
    participant D as Decision engine
    participant L as Audit log
    C->>A: payment + trace ID
    A->>F: read point-in-time features
    A->>G: read point-in-time graph signals
    F-->>A: prior-event windows
    G-->>A: prior connected-entity risk
    Note over F,G: Current event is inserted only after reads
    A->>M: identical feature vector
    M-->>A: champion and shadow scores
    A->>D: champion fused risk
    D-->>A: approve / review / decline
    A->>L: decision, versions, reasons, signals, latency
    A-->>C: auditable response
```

The application intentionally keeps the reference deployment in one process. This makes
state transitions and benchmarks reproducible without pretending to solve distributed
ordering. ADR 001 describes what must change for a multi-instance deployment.

## Components

| Component | Responsibility | State |
|---|---|---|
| FastAPI | Validate authorization payloads and expose dashboard/control APIs | None |
| OnlineFeatureStore | Customer temporal windows and historical aggregates | In memory |
| FraudGraph | Entity edges, structural features, confirmed-fraud counters | In memory |
| RiskModel | XGBoost, Isolation Forest, fusion, native TreeSHAP values | Fitted objects |
| DecisionEngine | Threshold optimization and action selection | Costs + thresholds |
| Audit log | Traceable response records and dashboard feed | Bounded in memory |
| Benchmark | Point-in-time replay, metrics, latency, metadata, figures | Files |

## Consistency boundary

`FraudDecisionService.authorize` serializes state mutation with a re-entrant lock. This
ensures each process has deterministic read-before-write semantics. It also limits local
concurrency and is explicitly not evidence of distributed correctness or capacity.

## Feedback path

Authorization requests never contain labels. Offline replay queues simulated confirmed fraud
and releases it into graph statistics only after the configured delay. A real deployment
would replace that queue with an idempotent chargeback/analyst-outcome stream.

