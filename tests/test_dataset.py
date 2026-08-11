from datetime import timedelta

from fraud_engine.dataset import build_point_in_time_dataset, chronological_split
from fraud_engine.simulator import PaymentSimulator, ScenarioConfig


def test_chronological_split_has_fraud_in_each_partition() -> None:
    events = PaymentSimulator(
        ScenarioConfig(normal_events=300, fraud_events_per_pattern=6)
    ).generate()
    records = build_point_in_time_dataset(events, confirmation_delay=timedelta(minutes=30))
    partitions = chronological_split(records)
    assert all(any(record.label for record in partition) for partition in partitions)
    assert partitions[0][-1].event.event_time <= partitions[1][0].event.event_time


def test_confirmation_delay_blocks_immediate_label_feedback() -> None:
    events = PaymentSimulator(
        ScenarioConfig(
            normal_events=20,
            fraud_events_per_pattern=2,
            enabled_patterns=("coordinated_ring",),
        )
    ).generate()
    records = build_point_in_time_dataset(events, confirmation_delay=timedelta(days=1))
    assert all(record.features["neighborhood_confirmed_fraud_rate"] == 0 for record in records)
