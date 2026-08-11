from __future__ import annotations

import ipaddress
import math
import random
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from fraud_engine.domain import AuthenticationMethod, PaymentEvent

COUNTRIES = {
    "FR": (48.8566, 2.3522, "EUR"),
    "DE": (52.5200, 13.4050, "EUR"),
    "GB": (51.5074, -0.1278, "GBP"),
    "US": (40.7128, -74.0060, "USD"),
    "SG": (1.3521, 103.8198, "SGD"),
    "BR": (-23.5505, -46.6333, "BRL"),
}
MCCS = ["grocery", "fuel", "restaurant", "electronics", "travel", "gaming", "luxury"]
AUTH_METHODS = list(AuthenticationMethod)
FRAUD_PATTERNS = {
    "account_takeover",
    "card_testing",
    "impossible_travel",
    "unusual_merchant",
    "high_velocity",
    "new_device",
    "transaction_burst",
    "compromised_merchant",
    "coordinated_ring",
}


@dataclass(frozen=True)
class ScenarioConfig:
    seed: int = 7
    customers: int = 250
    cards_per_customer: int = 1
    merchants: int = 50
    normal_events: int = 2_000
    fraud_events_per_pattern: int = 20
    enabled_patterns: tuple[str, ...] = tuple(sorted(FRAUD_PATTERNS))
    start_time: datetime = datetime(2026, 1, 1, tzinfo=UTC)

    def __post_init__(self) -> None:
        unknown = set(self.enabled_patterns) - FRAUD_PATTERNS
        if unknown:
            raise ValueError(f"unknown fraud patterns: {sorted(unknown)}")


class PaymentSimulator:
    """Deterministic event-time simulator with documented, configurable attacks."""

    def __init__(self, config: ScenarioConfig) -> None:
        self.config = config
        self.rng = random.Random(config.seed)
        self.customers = [f"cus_{index:05d}" for index in range(config.customers)]
        self.cards = {
            customer: [f"card_{customer[4:]}_{index}" for index in range(config.cards_per_customer)]
            for customer in self.customers
        }
        self.merchants = [f"mer_{index:04d}" for index in range(config.merchants)]
        self.home_country = {
            customer: self.rng.choice(list(COUNTRIES)) for customer in self.customers
        }
        self.base_amount = {customer: self.rng.uniform(18, 180) for customer in self.customers}
        self.devices = {customer: f"dev_{customer[4:]}_primary" for customer in self.customers}

    def _ip(self, seed: int) -> str:
        return str(ipaddress.ip_address(0x0A000000 + (seed % 0x00FFFFFF)))

    def _event(
        self,
        index: int,
        event_time: datetime,
        customer: str,
        *,
        fraud_pattern: str | None = None,
        overrides: dict[str, object] | None = None,
    ) -> PaymentEvent:
        country = self.home_country[customer]
        lat, lon, currency = COUNTRIES[country]
        values: dict[str, object] = {
            "transaction_id": f"txn_{index:08d}",
            "trace_id": f"trace_{index:08d}",
            "event_time": event_time,
            "customer_id": customer,
            "card_id": self.rng.choice(self.cards[customer]),
            "merchant_id": self.rng.choice(self.merchants),
            "amount": round(
                max(1.0, self.rng.lognormvariate(math.log(self.base_amount[customer]), 0.5)), 2
            ),
            "currency": currency,
            "country": country,
            "ip_address": self._ip(index * 7919),
            "device_id": self.devices[customer],
            "merchant_category": self.rng.choice(MCCS[:4]),
            "authentication_method": self.rng.choice(AUTH_METHODS),
            "authentication_successful": self.rng.random() > 0.03,
            "latitude": lat + self.rng.uniform(-0.2, 0.2),
            "longitude": lon + self.rng.uniform(-0.2, 0.2),
            "is_fraud": fraud_pattern is not None,
            "fraud_pattern": fraud_pattern,
        }
        if overrides:
            values.update(overrides)
        return PaymentEvent.model_validate(values)

    def _fraud_events(self, start_index: int, start: datetime) -> list[PaymentEvent]:
        events: list[PaymentEvent] = []
        size = self.config.fraud_events_per_pattern
        for pattern_index, pattern in enumerate(self.config.enabled_patterns):
            victims = self.rng.sample(self.customers, min(max(4, size // 3), len(self.customers)))
            shared_device = f"dev_ring_{pattern_index}"
            shared_ip = self._ip(15_000_000 + pattern_index)
            compromised = self.merchants[pattern_index % len(self.merchants)]
            for offset in range(size):
                customer = victims[offset % len(victims)]
                when = start + timedelta(seconds=pattern_index * (size + 5) + offset * 2)
                overrides: dict[str, object] = {"amount": round(self.rng.uniform(150, 900), 2)}
                if pattern == "account_takeover":
                    overrides.update(
                        device_id=f"dev_ato_{customer}", authentication_method="card_not_present"
                    )
                elif pattern == "card_testing":
                    overrides.update(
                        amount=round(self.rng.uniform(0.5, 3), 2),
                        device_id=shared_device,
                        ip_address=shared_ip,
                    )
                elif pattern == "impossible_travel":
                    foreign = "SG" if self.home_country[customer] != "SG" else "BR"
                    lat, lon, currency = COUNTRIES[foreign]
                    overrides.update(
                        country=foreign, latitude=lat, longitude=lon, currency=currency
                    )
                elif pattern == "unusual_merchant":
                    overrides.update(
                        merchant_category="luxury", amount=round(self.rng.uniform(800, 4_000), 2)
                    )
                elif pattern in {"high_velocity", "transaction_burst"}:
                    when = start + timedelta(seconds=pattern_index * 90 + offset % 4)
                elif pattern == "new_device":
                    overrides.update(device_id=f"dev_new_{start_index + len(events)}")
                elif pattern == "compromised_merchant":
                    overrides.update(merchant_id=compromised, device_id=f"dev_comp_{offset % 3}")
                elif pattern == "coordinated_ring":
                    overrides.update(
                        device_id=shared_device, ip_address=shared_ip, merchant_id=compromised
                    )
                events.append(
                    self._event(
                        start_index + len(events),
                        when,
                        customer,
                        fraud_pattern=pattern,
                        overrides=overrides,
                    )
                )
        return events

    def generate(self) -> list[PaymentEvent]:
        events: list[PaymentEvent] = []
        for index in range(self.config.normal_events):
            customer = self.rng.choice(self.customers)
            when = self.config.start_time + timedelta(seconds=index * 30 + self.rng.randint(0, 10))
            events.append(self._event(index, when, customer))
        fraud_start = self.config.start_time + timedelta(
            seconds=self.config.normal_events * 30 + 60
        )
        events.extend(self._fraud_events(len(events), fraud_start))
        return sorted(events, key=lambda event: (event.event_time, event.transaction_id))

    def stream(self) -> Iterator[PaymentEvent]:
        yield from self.generate()
