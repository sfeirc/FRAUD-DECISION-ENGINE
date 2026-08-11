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
    DecisionExplanation,
    ShadowResult,
)
from fraud_engine.features import OnlineFeatureStore
from fraud_engine.graph import FraudGraph
from fraud_engine.metrics import classification_and_business_metrics
from fraud_engine.modeling import ModelConfig, RiskModel, ScoredPayment
from fraud_engine.simulator import PaymentSimulator, ScenarioConfig


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
    ) -> None:
        self.champion = champion
        self.challenger = challenger
        self.engine = engine
        self.validation_records = validation_records
        self.feature_store = OnlineFeatureStore()
        self.graph = FraudGraph()
        self.audit_log: deque[dict[str, object]] = deque(maxlen=2_000)
        self.latencies_ms: deque[float] = deque(maxlen=10_000)
        self._lock = RLock()

    @classmethod
    def train_default(cls, *, seed: int = 7, normal_events: int = 1_200) -> FraudDecisionService:
        events = PaymentSimulator(
            ScenarioConfig(
                seed=seed,
                customers=180,
                normal_events=normal_events,
                fraud_events_per_pattern=18,
            )
        ).generate()
        records = build_point_in_time_dataset(events)
        train, validation, _ = chronological_split(records)
        train_rows = [record.features for record in train]
        train_labels = [record.label for record in train]
        champion = RiskModel(
            ModelConfig(
                version="champion-2.0",
                n_estimators=120,
                max_depth=4,
                learning_rate=0.05,
                supervised_weight=0.85,
                anomaly_weight=0.10,
                graph_weight=0.05,
            )
        ).fit(train_rows, train_labels)
        challenger = RiskModel(
            ModelConfig(
                version="challenger-2.1",
                n_estimators=120,
                max_depth=4,
                learning_rate=0.05,
                supervised_weight=0.90,
                anomaly_weight=0.05,
                graph_weight=0.05,
            )
        ).fit(train_rows, train_labels)
        engine = DecisionEngine()
        scores = champion.predict_risk_many(
            [row.features for row in validation], [row.graph_score for row in validation]
        )
        engine.optimize(
            scores,
            [row.label for row in validation],
            [row.event.amount for row in validation],
        )
        return cls(champion, challenger, engine, validation)

    def authorize(self, event: AuthorizationRequest) -> AuthorizationResponse:
        started = time.perf_counter_ns()
        with self._lock:
            temporal = self.feature_store.compute(event)
            graph_snapshot = self.graph.compute(event)
            features = {**temporal, **graph_snapshot.features}
            champion = self.champion.predict(features, graph_snapshot.graph_score)
            challenger = self.challenger.predict(
                features, graph_snapshot.graph_score, explain=False
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
        return {
            "status": "ok",
            "champion": self.champion.config.version,
            "challenger": self.challenger.config.version,
            "decisions": len(self.audit_log),
            "latency_ms": {
                "p50": float(np.percentile(values, 50)),
                "p95": float(np.percentile(values, 95)),
                "p99": float(np.percentile(values, 99)),
            },
        }

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
