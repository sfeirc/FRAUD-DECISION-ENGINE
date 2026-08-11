from sklearn.metrics import average_precision_score

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
    all_scores = [first.predict(row.features, row.graph_score).risk_score for row in test]
    assert average_precision_score([row.label for row in test], all_scores) >= 0.45
