from __future__ import annotations

import argparse
import csv
import importlib.metadata
import json
import os
import platform
import subprocess
import time
from collections.abc import Mapping
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from fraud_engine.dataset import build_point_in_time_dataset, chronological_split
from fraud_engine.decisioning import DecisionEngine
from fraud_engine.domain import AuthorizationRequest
from fraud_engine.metrics import classification_and_business_metrics
from fraud_engine.modeling import ModelConfig, RiskModel
from fraud_engine.service import FraudDecisionService
from fraud_engine.simulator import PaymentSimulator, ScenarioConfig


def _version(package: str) -> str:
    try:
        return importlib.metadata.version(package)
    except importlib.metadata.PackageNotFoundError:
        return "not-installed"


def environment_metadata() -> dict[str, object]:
    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        commit = "unknown"
    return {
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "commit_hash": commit,
        "hardware": {
            "processor": platform.processor() or "unknown",
            "machine": platform.machine(),
            "logical_cpu_count": os.cpu_count(),
        },
        "operating_system": {
            "system": platform.system(),
            "release": platform.release(),
            "version": platform.version(),
        },
        "software": {
            "python": platform.python_version(),
            "fraud-decision-engine": _version("fraud-decision-engine"),
            "numpy": _version("numpy"),
            "scikit-learn": _version("scikit-learn"),
            "xgboost": _version("xgboost"),
            "networkx": _version("networkx"),
        },
    }


def _metric_svg(metrics: Mapping[str, object], output: Path) -> None:
    keys = ["pr_auc", "roc_auc", "precision", "recall", "recall_at_fixed_fpr"]
    labels = ["PR-AUC", "ROC-AUC", "Precision", "Recall", "Recall @ 1% FPR"]
    width, height = 720, 300
    bars = []
    for index, (key, label) in enumerate(zip(keys, labels, strict=True)):
        raw_value = metrics[key]
        if not isinstance(raw_value, (float, int)):
            raise TypeError(f"metric {key} must be numeric")
        value = float(raw_value)
        y = 48 + index * 46
        bars.append(
            f'<text x="20" y="{y + 16}" fill="#c9d8e8" font-size="13">{label}</text>'
            f'<rect x="175" y="{y}" width="{value * 470:.1f}" height="22" rx="4" fill="#34d6c6"/>'
            f'<text x="{185 + value * 470:.1f}" y="{y + 16}" '
            f'fill="#e8f0f8" font-size="12">{value:.4f}</text>'
        )
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}"><rect width="100%" height="100%" fill="#0d1b2d"/>'
        '<text x="20" y="27" fill="#e8f0f8" font-size="17" font-weight="700">'
        "Held-out fraud detection metrics</text>" + "".join(bars) + "</svg>"
    )
    output.write_text(svg, encoding="utf-8")


def _latency_svg(latency: dict[str, float], output: Path) -> None:
    keys = ["p50", "p95", "p99"]
    maximum = max(latency.values()) or 1
    bars = []
    for index, key in enumerate(keys):
        value = latency[key]
        x = 130 + index * 180
        height = 180 * value / maximum
        bars.append(
            f'<rect x="{x}" y="{245 - height:.1f}" width="90" '
            f'height="{height:.1f}" rx="5" fill="#f7b955"/>'
            f'<text x="{x + 23}" y="270" fill="#c9d8e8" font-size="13">{key.upper()}</text>'
            f'<text x="{x + 18}" y="{230 - height:.1f}" '
            f'fill="#e8f0f8" font-size="12">{value:.3f} ms</text>'
        )
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="720" height="300" viewBox="0 0 720 300">'
        '<rect width="100%" height="100%" fill="#0d1b2d"/>'
        '<text x="20" y="27" fill="#e8f0f8" font-size="17" font-weight="700">'
        "In-process authorization latency</text>" + "".join(bars) + "</svg>"
    )
    output.write_text(svg, encoding="utf-8")


def run_benchmark(
    output_dir: Path, *, normal_events: int = 2_000, seed: int = 7
) -> dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)
    scenario = ScenarioConfig(
        seed=seed,
        customers=250,
        merchants=50,
        normal_events=normal_events,
        fraud_events_per_pattern=25,
    )
    events = PaymentSimulator(scenario).generate()
    feature_started = time.perf_counter()
    records = build_point_in_time_dataset(events)
    feature_seconds = time.perf_counter() - feature_started
    train, validation, test = chronological_split(records)
    champion_config = ModelConfig(version="champion-1.0", n_estimators=70, max_depth=3)
    challenger_config = ModelConfig(
        version="challenger-1.1",
        n_estimators=110,
        max_depth=4,
        supervised_weight=0.78,
        anomaly_weight=0.10,
        graph_weight=0.12,
    )
    champion = RiskModel(champion_config).fit(
        [row.features for row in train], [row.label for row in train]
    )
    challenger = RiskModel(challenger_config).fit(
        [row.features for row in train], [row.label for row in train]
    )
    validation_scores = [
        champion.predict(row.features, row.graph_score).risk_score for row in validation
    ]
    engine = DecisionEngine()
    engine.optimize(
        validation_scores,
        [row.label for row in validation],
        [row.event.amount for row in validation],
    )
    champion_scores = [champion.predict(row.features, row.graph_score).risk_score for row in test]
    challenger_scores = [
        challenger.predict(row.features, row.graph_score).risk_score for row in test
    ]
    labels = [row.label for row in test]
    amounts = [row.event.amount for row in test]
    champion_metrics = classification_and_business_metrics(champion_scores, labels, amounts, engine)
    challenger_metrics = classification_and_business_metrics(
        challenger_scores, labels, amounts, engine
    )
    service = FraudDecisionService(champion, challenger, engine, validation)
    latencies: list[float] = []
    raw_rows: list[dict[str, object]] = []
    for index, (record, champion_score, challenger_score) in enumerate(
        zip(test, champion_scores, challenger_scores, strict=True)
    ):
        request = AuthorizationRequest.model_validate(
            record.event.model_dump(exclude={"is_fraud", "fraud_pattern"})
        )
        response = service.authorize(request)
        latencies.append(response.latency_ms)
        raw_rows.append(
            {
                "row": index,
                "transaction_id": record.event.transaction_id,
                "event_time": record.event.event_time.isoformat(),
                "label": record.label,
                "fraud_pattern": record.event.fraud_pattern or "none",
                "amount": record.event.amount,
                "champion_score": champion_score,
                "challenger_score": challenger_score,
                "decision": engine.decide(champion_score).value,
                "online_latency_ms": response.latency_ms,
            }
        )
    latency_summary = {
        "p50": float(np.percentile(latencies, 50)),
        "p95": float(np.percentile(latencies, 95)),
        "p99": float(np.percentile(latencies, 99)),
    }
    summary: dict[str, object] = {
        **environment_metadata(),
        "configuration": {
            "scenario": asdict(scenario),
            "scenario_start_time": scenario.start_time.isoformat(),
            "split": {"train": len(train), "validation": len(validation), "test": len(test)},
            "champion": asdict(champion_config),
            "challenger": asdict(challenger_config),
            "cost_assumptions": asdict(engine.assumptions),
            "thresholds": asdict(engine.thresholds),
            "fixed_fpr": 0.01,
            "latency_scope": (
                "single process, warm model, sequential requests, includes "
                "feature/graph/model/explanation/audit; excludes HTTP transport"
            ),
        },
        "measurements": {
            "feature_replay_seconds": feature_seconds,
            "champion": champion_metrics,
            "challenger_shadow": challenger_metrics,
            "latency_ms": latency_summary,
            "raw_rows": len(raw_rows),
        },
    }
    with (output_dir / "raw_measurements.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(raw_rows[0]))
        writer.writeheader()
        writer.writerows(raw_rows)
    (output_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, default=str), encoding="utf-8"
    )
    _metric_svg(champion_metrics, output_dir / "quality_metrics.svg")
    _latency_svg(latency_summary, output_dir / "latency.svg")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the reproducible fraud benchmark")
    parser.add_argument("--output-dir", type=Path, default=Path("benchmarks/results/latest"))
    parser.add_argument("--normal-events", type=int, default=2_000)
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()
    summary = run_benchmark(args.output_dir, normal_events=args.normal_events, seed=args.seed)
    print(json.dumps(summary, indent=2, default=str))


if __name__ == "__main__":
    main()
