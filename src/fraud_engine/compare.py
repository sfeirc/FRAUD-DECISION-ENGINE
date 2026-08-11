from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, cast


def _get(summary: dict[str, Any], *path: str) -> float:
    value: Any = summary
    for key in path:
        value = value[key]
    if not isinstance(value, (float, int)):
        raise TypeError(f"{'.'.join(path)} must be numeric")
    return float(value)


def compare_summaries(baseline: dict[str, Any], optimized: dict[str, Any]) -> dict[str, object]:
    baseline_feature = _get(baseline, "measurements", "feature_replay_seconds")
    optimized_feature = _get(optimized, "measurements", "feature_replay_seconds")
    baseline_p99 = _get(baseline, "measurements", "latency_ms", "p99")
    optimized_p99 = _get(optimized, "measurements", "latency_ms", "p99")
    baseline_pr = _get(baseline, "measurements", "champion", "pr_auc")
    optimized_pr = _get(optimized, "measurements", "champion", "pr_auc")
    baseline_cost = _get(baseline, "measurements", "champion", "total_estimated_business_cost")
    optimized_cost = _get(optimized, "measurements", "champion", "total_estimated_business_cost")
    baseline_capture = _get(baseline, "measurements", "champion", "fraud_capture_rate")
    optimized_capture = _get(optimized, "measurements", "champion", "fraud_capture_rate")
    baseline_false_positives = _get(baseline, "measurements", "champion", "false_positives")
    optimized_false_positives = _get(optimized, "measurements", "champion", "false_positives")
    return {
        "baseline_commit": baseline["commit_hash"],
        "optimized_commit": optimized["commit_hash"],
        "feature_replay": {
            "baseline_seconds": baseline_feature,
            "optimized_seconds": optimized_feature,
            "speedup": baseline_feature / optimized_feature,
        },
        "decision_latency_p99_ms": {
            "baseline": baseline_p99,
            "optimized": optimized_p99,
            "reduction_fraction": 1 - optimized_p99 / baseline_p99,
        },
        "pr_auc": {
            "baseline": baseline_pr,
            "optimized": optimized_pr,
            "absolute_change": optimized_pr - baseline_pr,
        },
        "estimated_business_cost": {
            "baseline": baseline_cost,
            "optimized": optimized_cost,
            "reduction_fraction": 1 - optimized_cost / baseline_cost,
        },
        "fraud_capture_rate": {
            "baseline": baseline_capture,
            "optimized": optimized_capture,
            "absolute_change": optimized_capture - baseline_capture,
        },
        "false_positives": {
            "baseline": int(baseline_false_positives),
            "optimized": int(optimized_false_positives),
            "change": int(optimized_false_positives - baseline_false_positives),
        },
        "scope": (
            "Same synthetic scenario, seed, split, hardware, and cost assumptions. "
            "Latency remains sequential, warm, in-process, and excludes HTTP transport."
        ),
    }


def comparison_svg(comparison: dict[str, object]) -> str:
    feature = comparison["feature_replay"]
    latency = comparison["decision_latency_p99_ms"]
    quality = comparison["pr_auc"]
    cost = comparison["estimated_business_cost"]
    capture = comparison["fraud_capture_rate"]
    false_positives = comparison["false_positives"]
    if not all(
        isinstance(item, dict)
        for item in (feature, latency, quality, cost, capture, false_positives)
    ):
        raise TypeError("comparison sections must be mappings")
    feature_map = cast(dict[str, Any], feature)
    latency_map = cast(dict[str, Any], latency)
    quality_map = cast(dict[str, Any], quality)
    cost_map = cast(dict[str, Any], cost)
    capture_map = cast(dict[str, Any], capture)
    false_positive_map = cast(dict[str, Any], false_positives)
    cards = [
        ("Feature replay", f"{feature_map['speedup']:.1f}× faster", "#34d6c6"),
        ("P99 latency", f"{latency_map['reduction_fraction']:.1%} lower", "#60a5fa"),
        ("PR-AUC", f"+{quality_map['absolute_change']:.4f}", "#a78bfa"),
        ("Estimated cost", f"{cost_map['reduction_fraction']:.1%} lower", "#f7b955"),
        ("Fraud capture", f"+{capture_map['absolute_change']:.2%}", "#34d399"),
        ("False positives", f"+{false_positive_map['change']}", "#fb7185"),
    ]
    blocks = []
    for index, (label, value, color) in enumerate(cards):
        x = 24 + (index % 3) * 230
        y = 62 + (index // 3) * 115
        blocks.append(
            f'<rect x="{x}" y="{y}" width="208" height="92" rx="10" fill="#13263d"/>'
            f'<text x="{x + 16}" y="{y + 29}" fill="#8fa7bf" font-size="12">{label}</text>'
            f'<text x="{x + 16}" y="{y + 65}" fill="{color}" font-size="24" '
            f'font-weight="700">{value}</text>'
        )
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="720" height="310" '
        'viewBox="0 0 720 310"><rect width="100%" height="100%" fill="#0d1b2d"/>'
        '<text x="24" y="34" fill="#e8f0f8" font-size="19" font-weight="700">'
        "Measured optimization impact</text>"
        + "".join(blocks)
        + '<text x="24" y="294" fill="#8fa7bf" font-size="11">'
        "Same synthetic seed, split, hardware, and costs; "
        "false-positive trade-off shown.</text></svg>"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare two saved benchmark summaries")
    parser.add_argument("baseline", type=Path)
    parser.add_argument("optimized", type=Path)
    parser.add_argument("--output-dir", type=Path, default=Path("benchmarks/results/comparison"))
    args = parser.parse_args()
    baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
    optimized = json.loads(args.optimized.read_text(encoding="utf-8"))
    comparison = compare_summaries(baseline, optimized)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "comparison.json").write_text(
        json.dumps(comparison, indent=2), encoding="utf-8"
    )
    (args.output_dir / "comparison.svg").write_text(comparison_svg(comparison), encoding="utf-8")
    print(json.dumps(comparison, indent=2))


if __name__ == "__main__":
    main()
