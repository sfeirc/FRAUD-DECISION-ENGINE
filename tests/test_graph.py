from datetime import UTC, datetime, timedelta

from fraud_engine.domain import PaymentEvent
from fraud_engine.graph import FraudGraph


def event(customer: str, offset: int = 0) -> PaymentEvent:
    return PaymentEvent(
        event_time=datetime(2026, 1, 1, tzinfo=UTC) + timedelta(seconds=offset),
        customer_id=customer,
        card_id=f"card-{customer}",
        merchant_id="merchant-shared",
        amount=10,
        currency="EUR",
        country="FR",
        ip_address="10.0.0.9",
        device_id="device-shared",
        merchant_category="grocery",
        authentication_method="chip_pin",
        latitude=48.8,
        longitude=2.3,
    )


def test_graph_features_exclude_current_event() -> None:
    graph = FraudGraph()
    first = graph.compute(event("one"))
    second = graph.compute(event("two", 1))
    assert first.features["shared_device_customers"] == 0
    assert second.features["shared_device_customers"] == 1


def test_shared_entity_ring_is_exported() -> None:
    graph = FraudGraph()
    for index, customer in enumerate(("one", "two", "three")):
        graph.compute(event(customer, index))
    ring = graph.suspicious_subgraph(minimum_customers=3)
    kinds = {node["kind"] for node in ring["nodes"]}
    assert "device" in kinds
    assert "customer" in kinds
