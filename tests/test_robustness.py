import numpy as np

from fraud_engine.robustness import _bootstrap_interval, run_robustness


def test_bootstrap_interval_is_deterministic_and_contains_mean() -> None:
    values = [0.4, 0.5, 0.7, 0.8]
    first = _bootstrap_interval(values, np.random.default_rng(9))
    second = _bootstrap_interval(values, np.random.default_rng(9))
    assert first == second
    assert first["bootstrap_95_ci_lower"] <= first["mean"]
    assert first["bootstrap_95_ci_upper"] >= first["mean"]


def test_small_robustness_run_writes_raw_and_generated_outputs(tmp_path) -> None:
    summary = run_robustness(tmp_path, seeds=[13, 17], normal_events=120)
    assert len(summary["per_seed"]) == 2
    assert (tmp_path / "per_seed.csv").is_file()
    assert (tmp_path / "summary.json").is_file()
    assert (tmp_path / "robustness.svg").is_file()
