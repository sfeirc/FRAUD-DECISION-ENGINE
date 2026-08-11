from datetime import UTC, datetime, timedelta

from fraud_engine.domain import AuthenticationMethod, PaymentEvent
from fraud_engine.features import OnlineFeatureStore


def payment(when: datetime, *, amount: float = 10, device: str = "device-a") -> PaymentEvent:
    return PaymentEvent(
        transaction_id=f"txn-{when.timestamp()}",
        event_time=when,
        customer_id="customer-a",
        card_id="card-a",
        merchant_id="merchant-a",
        amount=amount,
        currency="EUR",
        country="FR",
        ip_address="10.0.0.1",
        device_id=device,
        merchant_category="grocery",
        authentication_method="chip_pin",
        latitude=48.8566,
        longitude=2.3522,
    )


def test_current_transaction_is_not_in_its_own_features() -> None:
    store = OnlineFeatureStore()
    first = store.compute(payment(datetime(2026, 1, 1, tzinfo=UTC), amount=10))
    second = store.compute(
        payment(datetime(2026, 1, 1, tzinfo=UTC) + timedelta(seconds=30), amount=20)
    )
    assert first["tx_count_1m"] == 0
    assert first["avg_amount_history"] == 10
    assert second["tx_count_1m"] == 1
    assert second["avg_amount_history"] == 10


def test_window_boundaries_and_new_device() -> None:
    store = OnlineFeatureStore()
    start = datetime(2026, 1, 1, tzinfo=UTC)
    store.compute(payment(start, device="known"))
    result = store.compute(payment(start + timedelta(minutes=61), device="new"))
    assert result["tx_count_1h"] == 0
    assert result["tx_count_1d"] == 1
    assert result["is_new_device"] == 1


def test_current_authentication_and_interarrival_features_are_available() -> None:
    store = OnlineFeatureStore()
    start = datetime(2026, 1, 1, tzinfo=UTC)
    store.compute(payment(start))
    failed = payment(start + timedelta(seconds=15)).model_copy(
        update={
            "authentication_successful": False,
            "authentication_method": AuthenticationMethod.CARD_NOT_PRESENT,
        }
    )
    result = store.compute(failed)
    assert result["authentication_failed"] == 1
    assert result["is_card_not_present"] == 1
    assert result["seconds_since_last_transaction"] == 15


def test_label_does_not_change_features() -> None:
    when = datetime(2026, 1, 1, tzinfo=UTC)
    legitimate = payment(when)
    fraudulent = legitimate.model_copy(update={"is_fraud": True, "fraud_pattern": "test"})
    assert OnlineFeatureStore().compute(legitimate) == OnlineFeatureStore().compute(fraudulent)
