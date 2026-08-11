from fraud_engine.simulator import PaymentSimulator, ScenarioConfig


def test_simulator_is_reproducible() -> None:
    config = ScenarioConfig(normal_events=20, fraud_events_per_pattern=2)
    first = [event.model_dump(mode="json") for event in PaymentSimulator(config).generate()]
    second = [event.model_dump(mode="json") for event in PaymentSimulator(config).generate()]
    assert first == second


def test_all_configured_patterns_are_emitted() -> None:
    config = ScenarioConfig(normal_events=5, fraud_events_per_pattern=1)
    patterns = {
        event.fraud_pattern for event in PaymentSimulator(config).generate() if event.is_fraud
    }
    assert patterns == set(config.enabled_patterns)
