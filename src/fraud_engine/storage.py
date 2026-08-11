from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path

from fraud_engine.domain import AuthorizationRequest, AuthorizationResponse


class IdempotencyConflictError(RuntimeError):
    """The transaction ID already exists with a different request body."""


class LateEventError(RuntimeError):
    """The event is older than the accepted customer event-time watermark."""


def configured_database_path() -> Path:
    return Path(os.environ.get("FRAUD_DATABASE_PATH", "artifacts/runtime/fraud.sqlite3"))


class AuthorizationStore:
    """SQLite authorization journal with idempotency and per-customer watermarks."""

    def __init__(
        self, path: Path | str = ":memory:", *, allowed_lateness: timedelta = timedelta(minutes=5)
    ) -> None:
        self.path = str(path)
        self.allowed_lateness = allowed_lateness
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(self.path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.execute("PRAGMA synchronous=FULL")
        self._connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS authorizations (
                transaction_id TEXT PRIMARY KEY,
                request_hash TEXT NOT NULL,
                event_json TEXT NOT NULL,
                response_json TEXT NOT NULL,
                decision TEXT NOT NULL,
                risk_score REAL NOT NULL,
                latency_ms REAL NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_authorizations_created_at
                ON authorizations(created_at DESC);
            CREATE TABLE IF NOT EXISTS customer_watermarks (
                customer_id TEXT PRIMARY KEY,
                latest_event_time TEXT NOT NULL
            );
            """
        )

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        try:
            self._connection.execute("BEGIN IMMEDIATE")
            yield self._connection
            self._connection.commit()
        except Exception:
            self._connection.rollback()
            raise

    @staticmethod
    def _request_json(event: AuthorizationRequest) -> str:
        return event.model_dump_json(exclude_none=False)

    @classmethod
    def _request_hash(cls, event: AuthorizationRequest) -> str:
        return hashlib.sha256(cls._request_json(event).encode()).hexdigest()

    def cached_response(self, event: AuthorizationRequest) -> AuthorizationResponse | None:
        row = self._connection.execute(
            "SELECT request_hash, response_json FROM authorizations WHERE transaction_id = ?",
            (event.transaction_id,),
        ).fetchone()
        if row is None:
            return None
        if row["request_hash"] != self._request_hash(event):
            raise IdempotencyConflictError(
                f"transaction_id {event.transaction_id!r} was already used for another payload"
            )
        return AuthorizationResponse.model_validate_json(row["response_json"])

    def reject_if_late(self, event: AuthorizationRequest) -> None:
        row = self._connection.execute(
            "SELECT latest_event_time FROM customer_watermarks WHERE customer_id = ?",
            (event.customer_id,),
        ).fetchone()
        if row is None:
            return
        watermark = datetime.fromisoformat(row["latest_event_time"])
        if event.event_time < watermark - self.allowed_lateness:
            raise LateEventError(
                f"event_time is older than the {self.allowed_lateness} allowed-lateness policy"
            )

    def save(self, event: AuthorizationRequest, response: AuthorizationResponse) -> None:
        with self._transaction() as connection:
            connection.execute(
                """
                INSERT INTO authorizations (
                    transaction_id, request_hash, event_json, response_json, decision,
                    risk_score, latency_ms, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.transaction_id,
                    self._request_hash(event),
                    self._request_json(event),
                    response.model_dump_json(),
                    response.decision.value,
                    response.risk_score,
                    response.latency_ms,
                    response.timestamp.isoformat(),
                ),
            )
            connection.execute(
                """
                INSERT INTO customer_watermarks(customer_id, latest_event_time) VALUES (?, ?)
                ON CONFLICT(customer_id) DO UPDATE
                SET latest_event_time = excluded.latest_event_time
                WHERE excluded.latest_event_time > customer_watermarks.latest_event_time
                """,
                (event.customer_id, event.event_time.isoformat()),
            )

    def recent(self, limit: int) -> list[dict[str, object]]:
        rows = self._connection.execute(
            """
            SELECT event_json, response_json FROM authorizations
            ORDER BY created_at DESC LIMIT ?
            """,
            (min(max(limit, 1), 500),),
        ).fetchall()
        results = []
        for row in rows:
            event = json.loads(row["event_json"])
            response = json.loads(row["response_json"])
            results.append(
                {
                    "transaction_id": event["transaction_id"],
                    "amount": event["amount"],
                    **response,
                }
            )
        return results

    def decision_counts(self) -> dict[str, int]:
        rows = self._connection.execute(
            "SELECT decision, COUNT(*) AS count FROM authorizations GROUP BY decision"
        ).fetchall()
        return {str(row["decision"]): int(row["count"]) for row in rows}

    def count(self) -> int:
        row = self._connection.execute("SELECT COUNT(*) AS count FROM authorizations").fetchone()
        return int(row["count"])

    def close(self) -> None:
        self._connection.close()
