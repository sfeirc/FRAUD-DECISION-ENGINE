from pytest import approx
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
    # This intentionally small 10-tree smoke model has measured platform variance;
    # 0.40 is the observed cross-platform regression floor, not a champion claim.
    assert average_precision_score([row.label for row in test], all_scores) >= 0.40
    batch_scores = first.predict_risk_many(
        [row.features for row in test], [row.graph_score for row in test]
    )
    assert batch_scores == approx(all_scores)
    first_prediction = first.predict(test[0].features, test[0].graph_score)
    shared_anomaly_prediction = second.predict(
        test[0].features,
        test[0].graph_score,
        anomaly_score_override=first_prediction.anomaly_score,
    )
    assert shared_anomaly_prediction.risk_score == approx(first_prediction.risk_score)
    second.share_anomaly_model_from(first)
    assert second.anomaly is first.anomaly


def test_probability_calibration_is_fitted_separately_from_training() -> None:
    events = PaymentSimulator(
        ScenarioConfig(normal_events=300, fraud_events_per_pattern=6, seed=37)
    ).generate()
    train, validation, test = chronological_split(build_point_in_time_dataset(events))
    model = RiskModel(ModelConfig(version="calibration-test", n_estimators=12)).fit(
        [row.features for row in train], [row.label for row in train]
    )
    validation_scores = model.predict_risk_many(
        [row.features for row in validation], [row.graph_score for row in validation]
    )
    model.fit_calibrator(validation_scores, [row.label for row in validation])
    calibrated = model.predict_risk_many(
        [row.features for row in test], [row.graph_score for row in test]
    )
    assert model.calibrator is not None
    assert calibrated != validation_scores[: len(calibrated)]
    assert all(0 <= score <= 1 for score in calibrated)
