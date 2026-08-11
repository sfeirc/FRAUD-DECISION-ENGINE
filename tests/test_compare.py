from fraud_engine.compare import compare_summaries, comparison_svg


def summary(feature: float, p99: float, pr_auc: float, cost: float) -> dict[str, object]:
    return {
        "commit_hash": "abc",
        "measurements": {
            "feature_replay_seconds": feature,
            "latency_ms": {"p99": p99},
            "champion": {
                "pr_auc": pr_auc,
                "total_estimated_business_cost": cost,
                "fraud_capture_rate": 0.8,
                "false_positives": 5,
            },
        },
    }


def test_comparison_calculates_speed_and_tradeoffs() -> None:
    comparison = compare_summaries(summary(8, 40, 0.6, 2_000), summary(2, 30, 0.7, 1_500))
    assert comparison["feature_replay"]["speedup"] == 4  # type: ignore[index]
    assert comparison["decision_latency_p99_ms"]["reduction_fraction"] == 0.25  # type: ignore[index]
    assert "Measured optimization impact" in comparison_svg(comparison)
