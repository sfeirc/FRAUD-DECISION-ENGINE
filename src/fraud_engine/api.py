from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field

from fraud_engine import __version__
from fraud_engine.artifacts import load_artifact
from fraud_engine.decisioning import CostAssumptions
from fraud_engine.demo import run_scenario
from fraud_engine.domain import AuthorizationRequest, AuthorizationResponse
from fraud_engine.service import FraudDecisionService


class CostUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fraud_loss_rate: float = Field(default=1.0, ge=0)
    false_positive_decline_cost: float = Field(default=35.0, ge=0)
    false_positive_review_cost: float = Field(default=8.0, ge=0)
    manual_review_cost: float = Field(default=4.0, ge=0)
    operational_cost: float = Field(default=0.05, ge=0)
    review_fraud_capture_rate: float = Field(default=0.80, ge=0, le=1)


def create_app(service: FraudDecisionService | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if not hasattr(app.state, "fraud_service"):
            app.state.fraud_service = load_artifact()
        yield

    app = FastAPI(
        title="Aegis Fraud Decision Engine",
        version=__version__,
        description="Cost-sensitive payment decisions with temporal, anomaly, and graph risk.",
        lifespan=lifespan,
    )
    if service is not None:
        app.state.fraud_service = service

    def get_service(request: Request) -> FraudDecisionService:
        return request.app.state.fraud_service  # type: ignore[no-any-return]

    @app.post("/v1/payments/authorize", response_model=AuthorizationResponse)
    def authorize(payload: AuthorizationRequest, request: Request) -> AuthorizationResponse:
        return get_service(request).authorize(payload)

    @app.get("/v1/health")
    def health(request: Request) -> dict[str, object]:
        return get_service(request).health()

    @app.get("/v1/audit")
    def audit(request: Request, limit: int = 50) -> list[dict[str, object]]:
        log = get_service(request).audit_log
        return list(log)[-min(max(limit, 1), 500) :][::-1]

    @app.get("/v1/graph/rings")
    def rings(request: Request) -> dict[str, list[dict[str, object]]]:
        return get_service(request).graph.suspicious_subgraph()

    @app.get("/v1/models/shadow-comparison")
    def shadow_comparison(request: Request) -> dict[str, object]:
        return get_service(request).shadow_comparison()

    @app.put("/v1/decision-costs")
    def update_costs(payload: CostUpdate, request: Request) -> dict[str, object]:
        assumptions = CostAssumptions(**payload.model_dump())
        return get_service(request).update_costs(assumptions)

    @app.post("/v1/demo/run")
    def demo(request: Request) -> dict[str, object]:
        return run_scenario(get_service(request), normal_events=90, ring_events=18)

    @app.get("/dashboard", include_in_schema=False)
    def dashboard() -> FileResponse:
        return FileResponse(Path(__file__).parent / "static" / "dashboard.html")

    @app.get("/", include_in_schema=False)
    def root() -> FileResponse:
        return dashboard()

    return app


app = create_app()


def run() -> None:
    uvicorn.run("fraud_engine.api:app", host="0.0.0.0", port=8000, reload=False)
