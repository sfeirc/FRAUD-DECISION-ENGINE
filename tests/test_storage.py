from datetime import UTC, datetime, timedelta

import pytest

from fraud_engine.domain import (
    AuthorizationRequest,
    AuthorizationResponse,
    Decision,
    DecisionExplanation,
)
from fraud_engine.storage import AuthorizationStore, IdempotencyConflictError, LateEventError


def request(transaction_id: str = "storage-1", *, minutes: int = 0) -> AuthorizationRequest:
    return AuthorizationRequest(
        transaction_id=transaction_id,
        trace_id=f"trace-{transaction_id}",
        event_time=datetime(2026, 8, 1, 12, minutes, tzinfo=UTC),
        customer_id="customer-storage",
        card_id="card-storage",
        merchant_id="merchant-storage",
        amount=42.0,
        currency="EUR",
        country="FR",
        ip_address="10.0.0.8",
        device_id="device-storage",
        merchant_category="grocery",
        authentication_method="3ds",
        latitude=48.85,
        longitude=2.35,
    )


def response(event: AuthorizationRequest) -> AuthorizationResponse:
    return AuthorizationResponse(
        decision=Decision.APPROVE,
        risk_score=0.04,
        reason_codes=[],
        model_version="test-model",
        explanation=DecisionExplanation(
            top_contributing_factors=[],
            triggered_rules=[],
            graph_signals={},
            summary="low risk",
        ),
        timestamp=datetime(2026, 8, 1, 12, tzinfo=UTC),
        trace_id=event.trace_id,
        latency_ms=1.2,
    )


def test_sqlite_journal_survives_reopen_and_enforces_idempotency(tmp_path) -> None:
    path = tmp_path / "authorizations.sqlite3"
    event = request()
    first = AuthorizationStore(path)
    first.save(event, response(event))
    first.close()

    reopened = AuthorizationStore(path)
    assert reopened.cached_response(event) == response(event)
    assert reopened.count() == 1
    changed = event.model_copy(update={"amount": 99.0})
    with pytest.raises(IdempotencyConflictError):
        reopened.cached_response(changed)
    assert reopened.recent(1)[0]["transaction_id"] == event.transaction_id
    reopened.close()


def test_customer_watermark_rejects_events_beyond_allowed_lateness() -> None:
    store = AuthorizationStore(allowed_lateness=timedelta(minutes=5))
    newest = request("newest", minutes=20)
    store.save(newest, response(newest))
    store.reject_if_late(request("within-window", minutes=16))
    with pytest.raises(LateEventError):
        store.reject_if_late(request("too-late", minutes=10))
