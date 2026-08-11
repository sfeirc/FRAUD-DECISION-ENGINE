from __future__ import annotations

import json
from collections import Counter
from dataclasses import asdict
from datetime import timedelta
from pathlib import Path
from typing import TYPE_CHECKING

from fraud_engine.decisioning import CostAssumptions
from fraud_engine.domain import AuthorizationRequest, Decision
from fraud_engine.simulator import PaymentSimulator, ScenarioConfig

if TYPE_CHECKING:
    from fraud_engine.service import FraudDecisionService


def run_scenario(
    service: FraudDecisionService,
    *,
    normal_events: int = 90,
    ring_events: int = 18,
    run_id: str = "cli",
) -> dict[str, object]:
    simulator = PaymentSimulator(
        ScenarioConfig(
            seed=91,
            customers=40,
            merchants=15,
            normal_events=normal_events,
            fraud_events_per_pattern=ring_events,
            enabled_patterns=("coordinated_ring",),
        )
    )
    decisions: Counter[str] = Counter()
    fraud_amount = prevented = 0.0
    fraud_scores: list[float] = []
    normal_scores: list[float] = []
    explanations: list[dict[str, object]] = []
    generated = simulator.generate()
    normal = [event for event in generated if not event.is_fraud]
    fraud = [event for event in generated if event.is_fraud]
    fraud_start = normal[-1].event_time + timedelta(seconds=2)
    ordered_events = normal + [
        event.model_copy(update={"event_time": fraud_start + timedelta(seconds=index * 2)})
        for index, event in enumerate(fraud)
    ]
    for event in ordered_events:
        event = event.model_copy(
            update={
                "transaction_id": f"{run_id}-{event.transaction_id}",
                "trace_id": f"{run_id}-{event.trace_id}",
            }
        )
        request = AuthorizationRequest.model_validate(
            event.model_dump(exclude={"is_fraud", "fraud_pattern"})
        )
        response = service.authorize(request)
        decisions[response.decision.value] += 1
        if event.is_fraud:
            fraud_amount += event.amount
            fraud_scores.append(response.risk_score)
            if response.decision is Decision.DECLINE:
                prevented += event.amount
            if len(explanations) < 5:
                explanations.append(
                    {
                        "transaction_id": event.transaction_id,
                        "risk_score": response.risk_score,
                        "decision": response.decision.value,
                        "reason_codes": response.reason_codes,
                        "summary": response.explanation.summary,
                    }
                )
        else:
            normal_scores.append(response.risk_score)
    thresholds_before = asdict(service.engine.thresholds)
    cost_change = service.update_costs(
        CostAssumptions(
            fraud_loss_rate=1.0,
            false_positive_decline_cost=1_000.0,
            false_positive_review_cost=250.0,
            manual_review_cost=4.0,
            operational_cost=0.05,
            review_fraud_capture_rate=0.80,
            max_review_rate=0.05,
        )
    )
    return {
        "scenario": "normal traffic followed by a coordinated shared-device/shared-IP ring",
        "events": normal_events + ring_events,
        "decisions": dict(decisions),
        "fraud_amount": round(fraud_amount, 2),
        "estimated_fraud_prevented": round(prevented, 2),
        "mean_normal_risk": round(sum(normal_scores) / max(len(normal_scores), 1), 5),
        "mean_ring_risk": round(sum(fraud_scores) / max(len(fraud_scores), 1), 5),
        "ring": service.graph.suspicious_subgraph(),
        "example_explanations": explanations,
        "thresholds_before_cost_change": thresholds_before,
        "thresholds_after_cost_change": cost_change["thresholds"],
        "cost_change": "false-positive costs increased for the interactive sensitivity example",
        "measurement_scope": (
            "simulated labels and configured costs; not realized financial savings"
        ),
    }


def main() -> None:
    from fraud_engine.artifacts import load_artifact

    print("Loading checksum-verified champion and shadow challenger artifact...")
    service = load_artifact()
    result = run_scenario(service)
    output_dir = Path("artifacts/demo")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "latest.json"
    output_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    print(f"\nSaved auditable demo output to {output_path}")
    print("Run `fraud-api` and open http://localhost:8000/dashboard for the live dashboard.")


if __name__ == "__main__":
    main()
