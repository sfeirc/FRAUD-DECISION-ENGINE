from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from fraud_engine.domain import Decision


@dataclass(frozen=True)
class CostAssumptions:
    fraud_loss_rate: float = 1.0
    false_positive_decline_cost: float = 35.0
    false_positive_review_cost: float = 8.0
    manual_review_cost: float = 4.0
    operational_cost: float = 0.05
    review_fraud_capture_rate: float = 0.80


@dataclass(frozen=True)
class DecisionThresholds:
    review: float
    decline: float

    def __post_init__(self) -> None:
        if not 0 <= self.review < self.decline <= 1:
            raise ValueError("thresholds must satisfy 0 <= review < decline <= 1")


@dataclass(frozen=True)
class CostBreakdown:
    fraud_loss: float
    false_positive_cost: float
    manual_review_cost: float
    operational_cost: float

    @property
    def total(self) -> float:
        return (
            self.fraud_loss
            + self.false_positive_cost
            + self.manual_review_cost
            + self.operational_cost
        )


class DecisionEngine:
    def __init__(
        self,
        assumptions: CostAssumptions | None = None,
        thresholds: DecisionThresholds | None = None,
    ) -> None:
        self.assumptions = assumptions or CostAssumptions()
        self.thresholds = thresholds or DecisionThresholds(review=0.45, decline=0.75)

    def decide(self, risk_score: float) -> Decision:
        if risk_score >= self.thresholds.decline:
            return Decision.DECLINE
        if risk_score >= self.thresholds.review:
            return Decision.REVIEW
        return Decision.APPROVE

    def optimize(
        self,
        scores: list[float],
        labels: list[int],
        amounts: list[float],
        *,
        grid_size: int = 41,
    ) -> DecisionThresholds:
        candidates = np.linspace(0.02, 0.98, grid_size)
        best_cost = float("inf")
        best = self.thresholds
        for review in candidates[:-1]:
            for decline in candidates[candidates > review]:
                thresholds = DecisionThresholds(float(review), float(decline))
                cost = self.evaluate(scores, labels, amounts, thresholds=thresholds).total
                if cost < best_cost:
                    best_cost = cost
                    best = thresholds
        self.thresholds = best
        return best

    def evaluate(
        self,
        scores: list[float],
        labels: list[int],
        amounts: list[float],
        *,
        thresholds: DecisionThresholds | None = None,
    ) -> CostBreakdown:
        selected = thresholds or self.thresholds
        fraud_loss = false_positive = review_cost = operational = 0.0
        for score, label, amount in zip(scores, labels, amounts, strict=True):
            decision = self._decide_with(score, selected)
            operational += self.assumptions.operational_cost
            if decision is Decision.APPROVE and label:
                fraud_loss += amount * self.assumptions.fraud_loss_rate
            elif decision is Decision.REVIEW:
                review_cost += self.assumptions.manual_review_cost
                if label:
                    fraud_loss += (
                        amount
                        * self.assumptions.fraud_loss_rate
                        * (1 - self.assumptions.review_fraud_capture_rate)
                    )
                else:
                    false_positive += self.assumptions.false_positive_review_cost
            elif decision is Decision.DECLINE and not label:
                false_positive += self.assumptions.false_positive_decline_cost
        return CostBreakdown(fraud_loss, false_positive, review_cost, operational)

    @staticmethod
    def _decide_with(score: float, thresholds: DecisionThresholds) -> Decision:
        if score >= thresholds.decline:
            return Decision.DECLINE
        if score >= thresholds.review:
            return Decision.REVIEW
        return Decision.APPROVE
