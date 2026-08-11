from pytest import approx

from fraud_engine.dataset import build_point_in_time_dataset, chronological_split
from fraud_engine.modeling import ModelConfig, RiskModel
from fraud_engine.simulator import PaymentSimulator, ScenarioConfig


def test_model_fit_predict_is_reproducible() -> None:
    events = PaymentSimulator(
        ScenarioConfig(normal_events=250, fraud_events_per_pattern=5)
    ).generate()
    train, _, test = chronological_split(build_point_in_time_dataset(events))
    rows = [record.features for record in train]
    labels = [record.label for record in train]
    config = ModelConfig(version="test", n_estimators=10, max_depth=2)
    first = RiskModel(config).fit(rows, labels)
    second = RiskModel(config).fit(rows, labels)
    first_scores = [first.predict(row.features, row.graph_score).risk_score for row in test[:10]]
    second_scores = [second.predict(row.features, row.graph_score).risk_score for row in test[:10]]
    assert first_scores == second_scores
    assert first_scores[:5] == approx([0.285278, 0.311814, 0.294873, 0.301448, 0.326241], abs=1e-6)
