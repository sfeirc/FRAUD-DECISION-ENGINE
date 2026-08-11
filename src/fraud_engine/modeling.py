from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import xgboost as xgb
from sklearn.ensemble import IsolationForest

from fraud_engine.features import ONLINE_FEATURE_NAMES
from fraud_engine.graph import GRAPH_FEATURE_NAMES

FEATURE_NAMES = ONLINE_FEATURE_NAMES + GRAPH_FEATURE_NAMES


@dataclass(frozen=True)
class ModelConfig:
    version: str
    n_estimators: int = 80
    max_depth: int = 4
    learning_rate: float = 0.08
    supervised_weight: float = 0.72
    anomaly_weight: float = 0.13
    graph_weight: float = 0.15
    random_state: int = 17


@dataclass(frozen=True)
class ScoredPayment:
    supervised_score: float
    anomaly_score: float
    graph_score: float
    risk_score: float
    contributions: list[dict[str, float | str]]


class RiskModel:
    """XGBoost + Isolation Forest fusion with native TreeSHAP contributions."""

    def __init__(self, config: ModelConfig) -> None:
        if not np.isclose(
            config.supervised_weight + config.anomaly_weight + config.graph_weight, 1.0
        ):
            raise ValueError("fusion weights must sum to one")
        self.config = config
        self.supervised: xgb.XGBClassifier | None = None
        self.anomaly: IsolationForest | None = None

    def fit(self, rows: list[dict[str, float]], labels: list[int]) -> RiskModel:
        matrix = self._matrix(rows)
        targets = np.asarray(labels)
        fraud_count = max(int(targets.sum()), 1)
        negative_count = max(len(targets) - fraud_count, 1)
        self.supervised = xgb.XGBClassifier(
            n_estimators=self.config.n_estimators,
            max_depth=self.config.max_depth,
            learning_rate=self.config.learning_rate,
            subsample=0.9,
            colsample_bytree=0.9,
            objective="binary:logistic",
            eval_metric="aucpr",
            scale_pos_weight=negative_count / fraud_count,
            random_state=self.config.random_state,
            n_jobs=1,
        )
        self.supervised.fit(matrix, targets)
        legitimate = matrix[targets == 0]
        self.anomaly = IsolationForest(
            n_estimators=100,
            contamination="auto",
            random_state=self.config.random_state,
            n_jobs=1,
        ).fit(legitimate)
        return self

    def predict(self, features: dict[str, float], graph_score: float) -> ScoredPayment:
        if self.supervised is None or self.anomaly is None:
            raise RuntimeError("model is not fitted")
        matrix = self._matrix([features])
        supervised_score = float(self.supervised.predict_proba(matrix)[0, 1])
        raw_anomaly = -float(self.anomaly.decision_function(matrix)[0])
        anomaly_score = float(1 / (1 + np.exp(-8 * raw_anomaly)))
        risk = (
            self.config.supervised_weight * supervised_score
            + self.config.anomaly_weight * anomaly_score
            + self.config.graph_weight * graph_score
        )
        booster = self.supervised.get_booster()
        contributions = booster.predict(xgb.DMatrix(matrix), pred_contribs=True)[0]
        ranked_pairs = sorted(
            (
                (name, round(float(value), 5))
                for name, value in zip(FEATURE_NAMES, contributions[:-1], strict=True)
            ),
            key=lambda item: abs(item[1]),
            reverse=True,
        )[:5]
        ranked: list[dict[str, float | str]] = [
            {"feature": name, "contribution": contribution} for name, contribution in ranked_pairs
        ]
        return ScoredPayment(
            supervised_score=supervised_score,
            anomaly_score=anomaly_score,
            graph_score=graph_score,
            risk_score=float(np.clip(risk, 0, 1)),
            contributions=ranked,
        )

    @staticmethod
    def _matrix(rows: list[dict[str, float]]) -> np.ndarray:
        return np.asarray(
            [[row.get(name, 0.0) for name in FEATURE_NAMES] for row in rows], dtype=float
        )
