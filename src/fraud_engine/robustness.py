from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import cast

import numpy as np

from fraud_engine.benchmark import environment_metadata
from fraud_engine.dataset import build_point_in_time_dataset, chronological_split
from fraud_engine.decisioning import DecisionEngine
from fraud_engine.metrics import classification_and_business_metrics
from fraud_engine.modeling import ModelConfig, RiskModel
from fraud_engine.simulator import PaymentSimulator, ScenarioConfig

ROBUSTNESS_METRICS = (
    "pr_auc",
    "recall_at_fixed_fpr",
    "fraud_capture_rate",
    "false_positives",
    "review_rate",
    "brier_score",
    "total_estimated_business_cost",
)


def evaluate_seed(seed: int, normal_events: int) -> dict[str, float | int]:
    scenario = ScenarioConfig(
        seed=seed,
        customers=250,
        merchants=50,
        normal_events=normal_events,
        fraud_events_per_pattern=25,
    )
    records = build_point_in_time_dataset(PaymentSimulator(scenario).generate())
    train, validation, test = chronological_split(records)
    config = ModelConfig(
        version="champion-3.0",
        n_estimators=120,
        max_depth=4,
        learning_rate=0.05,
        supervised_weight=0.85,
        anomaly_weight=0.10,
        graph_weight=0.05,
        anomaly_estimators=48,
    )
    model = RiskModel(config).fit([row.features for row in train], [row.label for row in train])
    validation_rows = [row.features for row in validation]
    validation_graph = [row.graph_score for row in validation]
    validation_labels = [row.label for row in validation]
    model.fit_calibrator(
        model.predict_risk_many(validation_rows, validation_graph), validation_labels
    )
    engine = DecisionEngine()
    engine.optimize(
        model.predict_risk_many(validation_rows, validation_graph),
        validation_labels,
        [row.event.amount for row in validation],
    )
    scores = model.predict_risk_many(
        [row.features for row in test], [row.graph_score for row in test]
    )
    metrics = classification_and_business_metrics(
        scores,
        [row.label for row in test],
        [row.event.amount for row in test],
        engine,
    )
    return {
        "seed": seed,
        "test_rows": len(test),
        "test_fraud_rows": sum(row.label for row in test),
        "review_threshold": engine.thresholds.review,
        "decline_threshold": engine.thresholds.decline,
        **{name: float(cast(float | int, metrics[name])) for name in ROBUSTNESS_METRICS},
    }


def _bootstrap_interval(values: list[float], rng: np.random.Generator) -> dict[str, float]:
    array = np.asarray(values, dtype=float)
    indices = rng.integers(0, len(array), size=(10_000, len(array)))
    means = array[indices].mean(axis=1)
    return {
        "mean": float(array.mean()),
        "sample_standard_deviation": float(array.std(ddof=1)) if len(array) > 1 else 0.0,
        "bootstrap_95_ci_lower": float(np.percentile(means, 2.5)),
        "bootstrap_95_ci_upper": float(np.percentile(means, 97.5)),
        "minimum": float(array.min()),
        "maximum": float(array.max()),
    }


def _robustness_svg(aggregates: dict[str, dict[str, float]], output: Path) -> None:
    selected = (
        ("pr_auc", "PR-AUC", "#34d6c6"),
        ("recall_at_fixed_fpr", "Recall @ 1% FPR", "#60a5fa"),
        ("fraud_capture_rate", "Fraud capture", "#a78bfa"),
        ("review_rate", "Review rate", "#f7b955"),
        ("brier_score", "Brier score", "#fb7185"),
    )
    blocks = []
    for index, (key, label, color) in enumerate(selected):
        aggregate = aggregates[key]
        y = 55 + index * 50
        mean = aggregate["mean"]
        lower = aggregate["bootstrap_95_ci_lower"]
        upper = aggregate["bootstrap_95_ci_upper"]
        x_mean = 190 + mean * 430
        x_lower = 190 + lower * 430
        x_upper = 190 + upper * 430
        blocks.append(
            f'<text x="20" y="{y + 15}" fill="#c9d8e8" font-size="13">{label}</text>'
            f'<line x1="190" y1="{y + 9}" x2="620" y2="{y + 9}" stroke="#29415d"/>'
            f'<line x1="{x_lower:.1f}" y1="{y + 9}" x2="{x_upper:.1f}" '
            f'y2="{y + 9}" stroke="{color}" stroke-width="5"/>'
            f'<circle cx="{x_mean:.1f}" cy="{y + 9}" r="6" fill="{color}"/>'
            f'<text x="635" y="{y + 15}" fill="#e8f0f8" font-size="12">{mean:.4f}</text>'
        )
    output.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="720" height="330" '
        'viewBox="0 0 720 330"><rect width="100%" height="100%" fill="#0d1b2d"/>'
        '<text x="20" y="28" fill="#e8f0f8" font-size="17" font-weight="700">'
        "Five-seed chronological evaluation</text>"
        + "".join(blocks)
        + '<text x="20" y="315" fill="#8fa7bf" font-size="11">'
        "Dots: seed mean; bars: deterministic bootstrap 95% interval of the mean.</text></svg>",
        encoding="utf-8",
    )


def run_robustness(
    output_dir: Path, *, seeds: list[int], normal_events: int = 2_000
) -> dict[str, object]:
    if len(seeds) < 2:
        raise ValueError("at least two seeds are required for uncertainty estimates")
    output_dir.mkdir(parents=True, exist_ok=True)
    rows = [evaluate_seed(seed, normal_events) for seed in seeds]
    rng = np.random.default_rng(20260811)
    aggregates = {
        metric: _bootstrap_interval([float(row[metric]) for row in rows], rng)
        for metric in ROBUSTNESS_METRICS
    }
    summary: dict[str, object] = {
        **environment_metadata(),
        "configuration": {
            "seeds": seeds,
            "normal_events_per_seed": normal_events,
            "chronological_split": {"train": 0.65, "validation": 0.15, "test": 0.20},
            "calibration": "Platt scaling fitted on each chronological validation partition",
            "threshold_selection": ("cost minimization on validation with maximum 5% review rate"),
            "uncertainty": (
                "10,000 deterministic non-parametric bootstrap resamples across seeds; "
                "interval describes seed-mean variation within this simulator"
            ),
        },
        "per_seed": rows,
        "aggregates": aggregates,
    }
    with (output_dir / "per_seed.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    (output_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, default=str) + "\n", encoding="utf-8"
    )
    _robustness_svg(aggregates, output_dir / "robustness.svg")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Run multi-seed chronological evaluation")
    parser.add_argument("--output-dir", type=Path, default=Path("benchmarks/results/robustness"))
    parser.add_argument("--seeds", type=int, nargs="+", default=[7, 19, 31, 43, 59])
    parser.add_argument("--normal-events", type=int, default=2_000)
    args = parser.parse_args()
    summary = run_robustness(args.output_dir, seeds=args.seeds, normal_events=args.normal_events)
    print(json.dumps(summary, indent=2, default=str))


if __name__ == "__main__":
    main()
