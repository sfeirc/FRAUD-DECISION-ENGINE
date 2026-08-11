from __future__ import annotations

from dataclasses import asdict

import numpy as np
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    precision_score,
    recall_score,
    roc_auc_score,
    roc_curve,
)

from fraud_engine.decisioning import DecisionEngine
from fraud_engine.domain import Decision


def classification_and_business_metrics(
    scores: list[float],
    labels: list[int],
    amounts: list[float],
    engine: DecisionEngine,
    *,
    fixed_fpr: float = 0.01,
) -> dict[str, float | int | dict[str, float]]:
    predictions = [int(score >= engine.thresholds.review) for score in scores]
    decisions = [engine.decide(score) for score in scores]
    labels_array = np.asarray(labels)
    scores_array = np.asarray(scores)
    if len(set(labels)) == 2:
        roc_auc = float(roc_auc_score(labels_array, scores_array))
        false_positive_rates, true_positive_rates, _ = roc_curve(labels_array, scores_array)
        eligible = true_positive_rates[false_positive_rates <= fixed_fpr]
        recall_at_fpr = float(eligible.max()) if eligible.size else 0.0
        pr_auc = float(average_precision_score(labels_array, scores_array))
    else:
        roc_auc = recall_at_fpr = pr_auc = float("nan")
    fraud_total = sum(amount for amount, label in zip(amounts, labels, strict=True) if label)
    fraud_prevented = sum(
        amount
        for amount, label, decision in zip(amounts, labels, decisions, strict=True)
        if label and decision is Decision.DECLINE
    )
    false_positives = sum(
        not label and decision is not Decision.APPROVE
        for label, decision in zip(labels, decisions, strict=True)
    )
    breakdown = engine.evaluate(scores, labels, amounts)
    calibration_bins = np.linspace(0, 1, 11)
    calibration_error = 0.0
    for lower, upper in zip(calibration_bins[:-1], calibration_bins[1:], strict=True):
        mask = (scores_array >= lower) & (
            scores_array <= upper if upper == 1 else scores_array < upper
        )
        if mask.any():
            calibration_error += float(mask.mean()) * abs(
                float(scores_array[mask].mean()) - float(labels_array[mask].mean())
            )
    return {
        "pr_auc": pr_auc,
        "roc_auc": roc_auc,
        "precision": float(precision_score(labels, predictions, zero_division=0)),
        "recall": float(recall_score(labels, predictions, zero_division=0)),
        "recall_at_fixed_fpr": recall_at_fpr,
        "brier_score": float(brier_score_loss(labels_array, scores_array)),
        "expected_calibration_error": calibration_error,
        "fixed_fpr": fixed_fpr,
        "fraud_amount": fraud_total,
        "fraud_captured_amount": fraud_prevented,
        "fraud_capture_rate": fraud_prevented / max(fraud_total, 1),
        "false_positives": int(false_positives),
        "manual_reviews": sum(decision is Decision.REVIEW for decision in decisions),
        "review_rate": sum(decision is Decision.REVIEW for decision in decisions)
        / max(len(decisions), 1),
        "estimated_fraud_prevented": fraud_prevented,
        "total_estimated_business_cost": breakdown.total,
        "cost_breakdown": asdict(breakdown),
    }
