from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import timedelta

from fraud_engine.domain import PaymentEvent
from fraud_engine.features import OnlineFeatureStore
from fraud_engine.graph import FraudGraph


@dataclass(frozen=True)
class FeatureRecord:
    event: PaymentEvent
    features: dict[str, float]
    graph_score: float
    label: int


def build_point_in_time_dataset(
    events: list[PaymentEvent], *, confirmation_delay: timedelta = timedelta(hours=2)
) -> list[FeatureRecord]:
    """Replay events using the same state transitions as online inference.

    Simulated labels become graph feedback only after ``confirmation_delay``. They are
    retained on output records for offline evaluation, never copied into features.
    """
    feature_store = OnlineFeatureStore()
    graph = FraudGraph()
    pending_confirmations: deque[PaymentEvent] = deque()
    records: list[FeatureRecord] = []
    ordered = sorted(events, key=lambda event: (event.event_time, event.transaction_id))
    for event in ordered:
        while (
            pending_confirmations
            and event.event_time - pending_confirmations[0].event_time >= confirmation_delay
        ):
            graph.confirm_fraud(pending_confirmations.popleft())
        temporal = feature_store.compute(event)
        graph_snapshot = graph.compute(event)
        records.append(
            FeatureRecord(
                event=event,
                features={**temporal, **graph_snapshot.features},
                graph_score=graph_snapshot.graph_score,
                label=int(bool(event.is_fraud)),
            )
        )
        if event.is_fraud:
            pending_confirmations.append(event)
    return records


def chronological_split(
    records: list[FeatureRecord], train_fraction: float = 0.65, validation_fraction: float = 0.15
) -> tuple[list[FeatureRecord], list[FeatureRecord], list[FeatureRecord]]:
    if not 0 < train_fraction < train_fraction + validation_fraction < 1:
        raise ValueError("split fractions must leave non-empty ordered partitions")
    train_end = int(len(records) * train_fraction)
    validation_end = int(len(records) * (train_fraction + validation_fraction))
    return records[:train_end], records[train_end:validation_end], records[validation_end:]
