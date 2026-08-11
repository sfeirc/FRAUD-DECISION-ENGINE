from datetime import UTC, datetime, timedelta

import networkx as nx

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


def test_component_index_matches_networkx_before_update() -> None:
    graph = FraudGraph()
    graph.compute(event("one"))
    graph.compute(event("two", 1))
    candidate = event("three", 2)
    snapshot = graph.compute(candidate, update=False)
    candidate_nodes = set(graph.event_nodes(candidate).values())
    expected_nodes = set(candidate_nodes)
    for node in candidate_nodes:
        if node in graph.graph:
            expected_nodes.update(nx.node_connected_component(graph.graph, node))
    assert snapshot.features["suspicious_component_size"] == len(expected_nodes)


def test_confirmed_fraud_aggregates_across_merged_components() -> None:
    graph = FraudGraph()
    fraudulent = event("one")
    graph.compute(fraudulent)
    graph.confirm_fraud(fraudulent)
    snapshot = graph.compute(event("two", 1), update=False)
    assert snapshot.features["neighborhood_confirmed_fraud_rate"] > 0
