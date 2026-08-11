from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AuthenticationMethod(StrEnum):
    CHIP_PIN = "chip_pin"
    CONTACTLESS = "contactless"
    THREE_DS = "3ds"
    WALLET = "wallet"
    CARD_NOT_PRESENT = "card_not_present"


class Decision(StrEnum):
    APPROVE = "approve"
    REVIEW = "review"
    DECLINE = "decline"


class PaymentEvent(BaseModel):
    """Immutable facts available at authorization time.

    ``is_fraud`` and ``fraud_pattern`` exist only on simulated/offline events. The API
    rejects them, and feature computation never reads them.
    """

    model_config = ConfigDict(extra="forbid")

    transaction_id: str = Field(default_factory=lambda: f"txn_{uuid4().hex}")
    trace_id: str = Field(default_factory=lambda: uuid4().hex)
    event_time: datetime = Field(default_factory=lambda: datetime.now(UTC))
    customer_id: str
    card_id: str
    merchant_id: str
    amount: float = Field(gt=0, le=1_000_000)
    currency: str = Field(min_length=3, max_length=3)
    country: str = Field(min_length=2, max_length=2)
    ip_address: str
    device_id: str
    merchant_category: str
    authentication_method: AuthenticationMethod
    authentication_successful: bool = True
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    is_fraud: bool | None = None
    fraud_pattern: str | None = None

    @field_validator("event_time")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("event_time must include a timezone")
        return value.astimezone(UTC)


class AuthorizationRequest(PaymentEvent):
    """Public API request: ground-truth labels are forbidden."""

    is_fraud: None = None
    fraud_pattern: None = None


class ModelPrediction(BaseModel):
    model_version: str
    supervised_score: float
    anomaly_score: float
    graph_score: float
    risk_score: float


class DecisionExplanation(BaseModel):
    top_contributing_factors: list[dict[str, float | str]]
    triggered_rules: list[str]
    graph_signals: dict[str, float]
    summary: str


class ShadowResult(BaseModel):
    model_version: str
    risk_score: float
    would_decide: Decision


class AuthorizationResponse(BaseModel):
    decision: Decision
    risk_score: float
    reason_codes: list[str]
    model_version: str
    explanation: DecisionExplanation
    timestamp: datetime
    trace_id: str
    latency_ms: float
    shadow: ShadowResult | None = None
