from __future__ import annotations

import math
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from fraud_engine.domain import PaymentEvent

ONLINE_FEATURE_NAMES = (
    "amount",
    "tx_count_1m",
    "tx_count_1h",
    "tx_count_1d",
    "spend_1h",
    "avg_amount_history",
    "amount_to_average_ratio",
    "distance_from_typical_km",
    "is_new_device",
    "is_new_merchant",
    "failed_auth_count_1h",
    "authentication_failed",
    "is_card_not_present",
    "is_high_risk_merchant_category",
    "seconds_since_last_transaction",
    "customer_history_count",
)


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6371.0088
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    value = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    )
    return radius * 2 * math.atan2(math.sqrt(value), math.sqrt(1 - value))


@dataclass
class CustomerState:
    transactions: deque[tuple[datetime, float, bool]] = field(default_factory=deque)
    total_amount: float = 0.0
    total_count: int = 0
    latitude_sum: float = 0.0
    longitude_sum: float = 0.0
    devices: set[str] = field(default_factory=set)
    merchants: set[str] = field(default_factory=set)
    last_event_time: datetime | None = None


class OnlineFeatureStore:
    """Stateful point-in-time feature store.

    Features are read from events strictly earlier than the current event, then the
    state is updated. Equal-timestamp ordering must be deterministic upstream.
    """

    def __init__(self) -> None:
        self._states: dict[str, CustomerState] = defaultdict(CustomerState)

    def compute(self, event: PaymentEvent, *, update: bool = True) -> dict[str, float]:
        state = self._states[event.customer_id]
        if state.last_event_time and event.event_time < state.last_event_time:
            raise ValueError(
                "events must be processed in non-decreasing event-time order per customer"
            )
        cutoff = event.event_time - timedelta(days=1)
        while state.transactions and state.transactions[0][0] < cutoff:
            state.transactions.popleft()
        minute = event.event_time - timedelta(minutes=1)
        hour = event.event_time - timedelta(hours=1)
        in_minute = [row for row in state.transactions if row[0] >= minute]
        in_hour = [row for row in state.transactions if row[0] >= hour]
        average = state.total_amount / state.total_count if state.total_count else event.amount
        typical_lat = (
            state.latitude_sum / state.total_count if state.total_count else event.latitude
        )
        typical_lon = (
            state.longitude_sum / state.total_count if state.total_count else event.longitude
        )
        features = {
            "amount": event.amount,
            "tx_count_1m": float(len(in_minute)),
            "tx_count_1h": float(len(in_hour)),
            "tx_count_1d": float(len(state.transactions)),
            "spend_1h": sum(row[1] for row in in_hour),
            "avg_amount_history": average,
            "amount_to_average_ratio": event.amount / max(average, 1.0),
            "distance_from_typical_km": haversine_km(
                typical_lat, typical_lon, event.latitude, event.longitude
            ),
            "is_new_device": float(event.device_id not in state.devices),
            "is_new_merchant": float(event.merchant_id not in state.merchants),
            "failed_auth_count_1h": float(sum(not row[2] for row in in_hour)),
            "authentication_failed": float(not event.authentication_successful),
            "is_card_not_present": float(
                event.authentication_method.value in {"card_not_present", "3ds"}
            ),
            "is_high_risk_merchant_category": float(
                event.merchant_category in {"gaming", "luxury", "travel"}
            ),
            "seconds_since_last_transaction": (
                min((event.event_time - state.last_event_time).total_seconds(), 86_400)
                if state.last_event_time
                else 86_400.0
            ),
            "customer_history_count": float(state.total_count),
        }
        if update:
            state.transactions.append(
                (event.event_time, event.amount, event.authentication_successful)
            )
            state.total_amount += event.amount
            state.total_count += 1
            state.latitude_sum += event.latitude
            state.longitude_sum += event.longitude
            state.devices.add(event.device_id)
            state.merchants.add(event.merchant_id)
            state.last_event_time = event.event_time
        return features

    def reset(self) -> None:
        self._states.clear()
