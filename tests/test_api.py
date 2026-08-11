from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from fraud_engine.api import create_app
from fraud_engine.service import FraudDecisionService


@pytest.fixture(scope="module")
def client() -> TestClient:
    service = FraudDecisionService.train_default(
        seed=19, normal_events=300, fraud_events_per_pattern=6
    )
    with TestClient(create_app(service)) as test_client:
        yield test_client


def valid_payload() -> dict[str, object]:
    return {
        "transaction_id": "api-test-1",
        "trace_id": "trace-api-test-1",
        "event_time": datetime(2026, 7, 1, tzinfo=UTC).isoformat(),
        "customer_id": "customer-api",
        "card_id": "card-api",
        "merchant_id": "merchant-api",
        "amount": 125.50,
        "currency": "EUR",
        "country": "FR",
        "ip_address": "10.1.2.3",
        "device_id": "device-api",
        "merchant_category": "electronics",
        "authentication_method": "3ds",
        "authentication_successful": True,
        "latitude": 48.8566,
        "longitude": 2.3522,
    }


def test_authorization_contract_and_shadow_prediction(client: TestClient) -> None:
    response = client.post("/v1/payments/authorize", json=valid_payload())
    assert response.status_code == 200
    body = response.json()
    assert body["decision"] in {"approve", "review", "decline"}
    assert body["model_version"].startswith("champion")
    assert body["shadow"]["model_version"].startswith("challenger")
    assert body["trace_id"] == "trace-api-test-1"
    assert body["latency_ms"] > 0
    health = client.get("/v1/health").json()
    assert "review_queue" in health
    assert health["thresholds"]["review"] < health["thresholds"]["decline"]


def test_labels_are_rejected_at_api_boundary(client: TestClient) -> None:
    payload = valid_payload()
    payload["is_fraud"] = True
    assert client.post("/v1/payments/authorize", json=payload).status_code == 422


def test_malformed_amount_is_rejected(client: TestClient) -> None:
    payload = valid_payload()
    payload["amount"] = -1
    assert client.post("/v1/payments/authorize", json=payload).status_code == 422


def test_decision_latency_guardrail(client: TestClient) -> None:
    latencies = []
    for index in range(10):
        payload = valid_payload()
        payload["transaction_id"] = f"latency-{index}"
        payload["trace_id"] = f"trace-latency-{index}"
        response = client.post("/v1/payments/authorize", json=payload)
        latencies.append(response.json()["latency_ms"])
    assert max(latencies) < 250


def test_killer_demo_builds_ring_and_changes_cost_thresholds(client: TestClient) -> None:
    response = client.post("/v1/demo/run")
    assert response.status_code == 200
    body = response.json()
    assert body["mean_ring_risk"] > body["mean_normal_risk"]
    assert len(body["ring"]["nodes"]) >= 5
    assert body["thresholds_before_cost_change"] != body["thresholds_after_cost_change"]
