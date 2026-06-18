from __future__ import annotations

import logging
import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

from .data_preprocessing import validate_records
from .decision_support import build_decision_support
from .forecasting import forecast_frame, simulate_budgets, train_model_bundle
from .gemini import generate_gemini_insights
from .schemas import (
    DecisionSupportRequest,
    DecisionSupportResponse,
    ForecastRequest,
    ForecastResponse,
    InsightsRequest,
    InsightsResponse,
    SimulationRequest,
    SimulationResponse,
    TrainRequest,
    TrainResponse,
    ValidationRequest,
    ValidationResponse,
)
from .utils import load_json_env


load_dotenv()

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="AIgnition ForecastIQ API",
    version="1.0.0",
    description="FastAPI backend for NetElixir AIgnition 3.0 ecommerce revenue and ROAS forecasting.",
)

allowed_origins = load_json_env(
    "CORS_ORIGINS",
    [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:4173",
        "http://127.0.0.1:4173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _validated_frame(records: list[dict], operation: str):
    """Validate request rows and return a clean frame or a client-safe 422."""
    frame, validation = validate_records(records)
    logger.info(
        "%s validation complete: %s/%s valid rows, %s issues",
        operation,
        validation.validRows,
        validation.totalRows,
        len(validation.issues),
    )
    if frame.empty:
        raise HTTPException(status_code=422, detail=f"No valid rows available for {operation}")
    return frame, validation


@app.get("/health")
def health() -> dict:
    """Return a cheap liveness probe for local and hosted deployments."""
    return {"status": "ok", "service": "forecastiq-api"}


@app.post("/api/validate", response_model=ValidationResponse)
def validate_data(request: ValidationRequest) -> ValidationResponse:
    """Validate uploaded campaign rows before they power forecasts."""
    _, validation = validate_records(request.rows)
    logger.info(
        "validate request complete: %s/%s valid rows, %s issues",
        validation.validRows,
        validation.totalRows,
        len(validation.issues),
    )
    return validation


@app.post("/api/forecast", response_model=ForecastResponse)
def forecast(request: ForecastRequest) -> ForecastResponse:
    """Generate revenue and ROAS forecasts for the requested planning level."""
    frame, validation = _validated_frame([row.model_dump() for row in request.rows], "forecasting")
    result = forecast_frame(frame, request.horizon, request.level, request.value)
    return ForecastResponse(
        revenue=result["revenue"],
        roas=result["roas"],
        summary=result["summary"],
        validation=validation,
    )


@app.post("/api/simulate", response_model=SimulationResponse)
def simulate(request: SimulationRequest) -> SimulationResponse:
    """Reforecast channel revenue after planned media budget changes."""
    frame, validation = _validated_frame([row.model_dump() for row in request.rows], "simulation")
    result = simulate_budgets(frame, request.horizon, request.budgets)
    return SimulationResponse(channels=result["channels"], totals=result["totals"], validation=validation)


@app.post("/api/decision-support", response_model=DecisionSupportResponse)
def decision_support(request: DecisionSupportRequest) -> DecisionSupportResponse:
    """Return optimizer, what-if, risk, opportunity and health analytics."""
    frame, validation = _validated_frame([row.model_dump() for row in request.rows], "decision support")
    result = build_decision_support(
        frame=frame,
        horizon=request.horizon,
        budgets=request.budgets,
        target_revenue=request.targetRevenue,
        target_roas=request.targetRoas,
        scenarios=request.scenarios,
    )
    return DecisionSupportResponse(**result, validation=validation)


@app.post("/api/insights", response_model=InsightsResponse)
async def insights(request: InsightsRequest) -> InsightsResponse:
    """Turn forecast and performance summaries into executive recommendations."""
    return await generate_gemini_insights(request.summary)


@app.post("/api/train", response_model=TrainResponse)
def train(request: TrainRequest) -> TrainResponse:
    """Train and persist the forecast model bundle from uploaded rows."""
    frame, validation = _validated_frame([row.model_dump() for row in request.rows], "training")
    bundle = train_model_bundle(frame, request.modelPath)
    return TrainResponse(
        modelPath=request.modelPath,
        modelType=bundle["model_type"],
        trainingRows=validation.validRows,
        message="Model bundle trained and persisted",
    )
