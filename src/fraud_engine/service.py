from __future__ import annotations

import time
from collections import deque
from dataclasses import asdict
from datetime import UTC, datetime
from threading import RLock

import numpy as np

from fraud_engine.dataset import FeatureRecord, build_point_in_time_dataset, chronological_split
from fraud_engine.decisioning import CostAssumptions, DecisionEngine
from fraud_engine.domain import (
    AuthorizationRequest,
    AuthorizationResponse,
    Decision,
    DecisionExplanation,
    ShadowResult,
)
from fraud_engine.features import OnlineFeatureStore
from fraud_engine.graph import FraudGraph
from fraud_engine.metrics import classification_and_business_metrics
from fraud_engine.modeling import ModelConfig, RiskModel, ScoredPayment
from fraud_engine.simulator import PaymentSimulator, ScenarioConfig
from fraud_engine.storage import AuthorizationStore


def reason_codes(features: dict[str, float], graph_score: float) -> list[str]:
    rules = []
    if features["is_new_device"]:
        rules.append("NEW_DEVICE")
    if features["tx_count_1m"] >= 3 or features["tx_count_1h"] >= 8:
        rules.append("HIGH_VELOCITY")
    if features["distance_from_typical_km"] >= 1_000:
        rules.append("UNUSUAL_COUNTRY")
    if features["amount_to_average_ratio"] >= 4:
        rules.append("AMOUNT_SPIKE")
    if features["shared_device_customers"] >= 3:
        rules.append("SHARED_DEVICE")
    if features["shared_ip_customers"] >= 3:
        rules.append("SHARED_IP")
    if graph_score >= 0.45:
        rules.append("GRAPH_CLUSTER_RISK")
    return rules


class FraudDecisionService:
    """Thread-safe in-process service used by the HTTP API and deterministic demo."""

    def __init__(
        self,
        champion: RiskModel,
        challenger: RiskModel,
        engine: DecisionEngine,
        validation_records: list[FeatureRecord],
        *,
        artifact_manifest: dict[str, object] | None = None,
        store: AuthorizationStore | None = None,
    ) -> None:
        self.champion = champion
        self.challenger = challenger
        self.engine = engine
        self.validation_records = validation_records
        self.artifact_manifest = artifact_manifest
        self.store = store or AuthorizationStore()
        self.feature_store = OnlineFeatureStore()
        self.graph = FraudGraph()
        self.audit_log: deque[dict[str, object]] = deque(maxlen=2_000)
        self.latencies_ms: deque[float] = deque(maxlen=10_000)
        self._lock = RLock()

    @classmethod
    def train_default(
        cls, *, seed: int = 7, normal_events: int = 2_000, fraud_events_per_pattern: int = 25
    ) -> FraudDecisionService:
        events = PaymentSimulator(
            ScenarioConfig(
                seed=seed,
                customers=250,
                normal_events=normal_events,
                fraud_events_per_pattern=fraud_events_per_pattern,
            )
        ).generate()
        records = build_point_in_time_dataset(events)
        train, validation, _ = chronological_split(records)
        train_rows = [record.features for record in train]
        train_labels = [record.label for record in train]
        champion = RiskModel(
            ModelConfig(
                version="champion-3.0",
                n_estimators=120,
                max_depth=4,
                learning_rate=0.05,
                supervised_weight=0.85,
                anomaly_weight=0.10,
                graph_weight=0.05,
                anomaly_estimators=48,
            )
        ).fit(train_rows, train_labels)
        challenger = RiskModel(
            ModelConfig(
                version="challenger-3.1",
                n_estimators=120,
                max_depth=4,
                learning_rate=0.05,
                supervised_weight=0.90,
                anomaly_weight=0.05,
                graph_weight=0.05,
                anomaly_estimators=48,
            )
        ).fit(train_rows, train_labels)
        challenger.share_anomaly_model_from(champion)
        engine = DecisionEngine()
        validation_rows = [row.features for row in validation]
        validation_graph_scores = [row.graph_score for row in validation]
        labels = [row.label for row in validation]
        champion.fit_calibrator(
            champion.predict_risk_many(validation_rows, validation_graph_scores), labels
        )
        challenger.fit_calibrator(
            challenger.predict_risk_many(validation_rows, validation_graph_scores), labels
        )
        scores = champion.predict_risk_many(validation_rows, validation_graph_scores)
        engine.optimize(
            scores,
            labels,
            [row.event.amount for row in validation],
        )
        return cls(champion, challenger, engine, validation)

    def authorize(self, event: AuthorizationRequest) -> AuthorizationResponse:
        started = time.perf_counter_ns()
        with self._lock:
            cached = self.store.cached_response(event)
            if cached is not None:
                return cached
            self.store.reject_if_late(event)
            temporal = self.feature_store.compute(event)
            graph_snapshot = self.graph.compute(event)
            features = {**temporal, **graph_snapshot.features}
            champion = self.champion.predict(features, graph_snapshot.graph_score)
            shared_anomaly = (
                champion.anomaly_score if self.champion.anomaly is self.challenger.anomaly else None
            )
            challenger = self.challenger.predict(
                features,
                graph_snapshot.graph_score,
                explain=False,
                anomaly_score_override=shared_anomaly,
            )
            decision = self.engine.decide(champion.risk_score)
            shadow_decision = self.engine.decide(challenger.risk_score)
            codes = reason_codes(features, graph_snapshot.graph_score)
            latency_ms = (time.perf_counter_ns() - started) / 1_000_000
            self.latencies_ms.append(latency_ms)
            response = AuthorizationResponse(
                decision=decision,
                risk_score=round(champion.risk_score, 6),
                reason_codes=codes,
                model_version=self.champion.config.version,
                explanation=self._explain(champion, codes, graph_snapshot.features),
                timestamp=datetime.now(UTC),
                trace_id=event.trace_id,
                latency_ms=round(latency_ms, 4),
                shadow=ShadowResult(
                    model_version=self.challenger.config.version,
                    risk_score=round(challenger.risk_score, 6),
                    would_decide=shadow_decision,
                ),
            )
            self.audit_log.append(
                {
                    "transaction_id": event.transaction_id,
                    "amount": event.amount,
                    **response.model_dump(mode="json"),
                }
            )
            self.store.save(event, response)
            return response

    def update_costs(self, assumptions: CostAssumptions) -> dict[str, object]:
        with self._lock:
            self.engine.assumptions = assumptions
            scores = self.champion.predict_risk_many(
                [row.features for row in self.validation_records],
                [row.graph_score for row in self.validation_records],
            )
            old = asdict(self.engine.thresholds)
            new = self.engine.optimize(
                scores,
                [row.label for row in self.validation_records],
                [row.event.amount for row in self.validation_records],
            )
            return {
                "previous_thresholds": old,
                "thresholds": asdict(new),
                "costs": asdict(assumptions),
            }

    def shadow_comparison(self) -> dict[str, object]:
        labels = [row.label for row in self.validation_records]
        amounts = [row.event.amount for row in self.validation_records]
        rows = [row.features for row in self.validation_records]
        graph_scores = [row.graph_score for row in self.validation_records]
        champion_scores = self.champion.predict_risk_many(rows, graph_scores)
        challenger_scores = self.challenger.predict_risk_many(rows, graph_scores)
        return {
            self.champion.config.version: classification_and_business_metrics(
                champion_scores, labels, amounts, self.engine
            ),
            self.challenger.config.version: classification_and_business_metrics(
                challenger_scores, labels, amounts, self.engine
            ),
            "note": (
                "Both models use the champion's active thresholds; "
                "challenger remains non-decisional."
            ),
        }

    def health(self) -> dict[str, object]:
        values = np.asarray(self.latencies_ms or [0.0])
        decision_counts = self.store.decision_counts()
        return {
            "status": "ok",
            "champion": self.champion.config.version,
            "challenger": self.challenger.config.version,
            "decisions": self.store.count(),
            "decision_counts": decision_counts,
            "review_queue": decision_counts.get(Decision.REVIEW.value, 0),
            "thresholds": asdict(self.engine.thresholds),
            "artifact": {
                "source_commit": self.artifact_manifest.get("source_commit"),
                "created_at_utc": self.artifact_manifest.get("created_at_utc"),
            }
            if self.artifact_manifest
            else None,
            "latency_ms": {
                "p50": float(np.percentile(values, 50)),
                "p95": float(np.percentile(values, 95)),
                "p99": float(np.percentile(values, 99)),
            },
        }

    def prometheus_metrics(self) -> str:
        health = self.health()
        latency = health["latency_ms"]
        if not isinstance(latency, dict):
            raise TypeError("latency health field must be a mapping")
        counts = self.store.decision_counts()
        lines = [
            "# HELP fraud_authorizations_total Persisted authorization decisions.",
            "# TYPE fraud_authorizations_total counter",
        ]
        for decision in Decision:
            lines.append(
                f'fraud_authorizations_total{{decision="{decision.value}"}} '
                f"{counts.get(decision.value, 0)}"
            )
        lines.extend(
            [
                "# HELP fraud_decision_latency_ms In-process decision latency percentiles.",
                "# TYPE fraud_decision_latency_ms gauge",
                *[
                    f'fraud_decision_latency_ms{{quantile="{quantile}"}} {latency[quantile]}'
                    for quantile in ("p50", "p95", "p99")
                ],
                "# HELP fraud_review_queue Current persisted review decisions.",
                "# TYPE fraud_review_queue gauge",
                f"fraud_review_queue {counts.get(Decision.REVIEW.value, 0)}",
            ]
        )
        return "\n".join(lines) + "\n"

    @staticmethod
    def _explain(
        score: ScoredPayment, codes: list[str], graph_signals: dict[str, float]
    ) -> DecisionExplanation:
        if codes:
            summary = "Risk elevated by " + ", ".join(
                code.lower().replace("_", " ") for code in codes
            )
        else:
            summary = (
                "No deterministic high-risk rule triggered; decision follows fused model score"
            )
        return DecisionExplanation(
            top_contributing_factors=score.contributions,
            triggered_rules=codes,
            graph_signals={key: round(value, 5) for key, value in graph_signals.items()},
            summary=summary,
        )
