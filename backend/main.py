from __future__ import annotations

import json
import logging
import os
from pathlib import Path

import joblib
from fastapi import FastAPI, Header, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from .data_preprocessing import validate_records
from .decision_support import build_decision_support, compute_driver_evidence, estimate_causal_effects
from .anomaly import compute_trend_breaks, detect_anomalies
from .forecasting import compute_spend_response_curve, forecast_frame, simulate_budgets
from .gemini import generate_gemini_insights
from .train import train_evaluator_model
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


load_dotenv()

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[os.getenv("SLOWAPI_DEFAULT_LIMITS", "200/hour")],
)
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parents[1]
MODEL_DIR = (PROJECT_ROOT / "pickle").resolve()

app = FastAPI(
    title="AIgnition ForecastIQ API",
    version="1.0.0",
    description="FastAPI backend for NetElixir AIgnition 3.0 ecommerce revenue and ROAS forecasting.",
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

DEFAULT_CORS_ORIGINS = [
    "http://localhost:5173",
    "http://localhost:5174",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:5174",
    "http://localhost:4173",
    "http://127.0.0.1:4173",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "https://ignite-forecast-iq.vercel.app",
]


def _load_cors_origins() -> list[str]:
    """Load safe defaults plus deployment origins without risking startup."""
    configured = _parse_cors_origin_config(os.getenv("CORS_ORIGINS"))
    return list(dict.fromkeys([*DEFAULT_CORS_ORIGINS, *configured]))


def _parse_cors_origin_config(raw: str | None) -> list[str]:
    """Parse comma-separated CORS origins, accepting legacy JSON arrays too."""
    if not raw or not raw.strip():
        return []
    value = raw.strip()
    if value.startswith("["):
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError:
            decoded = None
        if isinstance(decoded, list):
            return [_clean_origin(origin) for origin in decoded if _clean_origin(origin)]
    return [_clean_origin(origin) for origin in value.split(",") if _clean_origin(origin)]


def _clean_origin(origin: object) -> str:
    value = str(origin).strip().strip("\"'")
    if value != "*":
        value = value.rstrip("/")
    return value


allowed_origins = _load_cors_origins()

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
        detail = f"No valid rows available for {operation}"
        if validation.issues:
            detail = validation.issues[0].message
        raise HTTPException(status_code=422, detail=detail)
    return frame, validation


def _authorized_training_token(token: str | None) -> None:
    expected = (os.getenv("TRAINING_ADMIN_TOKEN") or "").strip()
    if not expected or token != expected:
        raise HTTPException(status_code=401, detail="Training admin token is required")


def _safe_model_path(model_path: str) -> Path:
    requested = Path(model_path)
    if requested.name != model_path and requested.parent not in {Path("."), Path("pickle")}:
        raise HTTPException(status_code=400, detail="modelPath must stay inside pickle/")
    resolved = (MODEL_DIR / requested.name).resolve()
    try:
        resolved.relative_to(MODEL_DIR)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="modelPath must stay inside pickle/") from exc
    if resolved.suffix != ".pkl":
        raise HTTPException(status_code=400, detail="modelPath must be a .pkl file")
    return resolved


@app.get("/health")
def health() -> dict:
    """Return a cheap liveness probe for local and hosted deployments."""
    return {"status": "ok", "service": "forecastiq-api"}


@app.head("/health")
def health_head() -> Response:
    """Support HEAD-based uptime checks without a response body."""
    return Response(status_code=200)


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
@limiter.limit("30/minute")
def forecast(request: Request, body: ForecastRequest) -> ForecastResponse:
    """Generate revenue and ROAS forecasts for the requested planning level."""
    frame, validation = _validated_frame([row.model_dump() for row in body.rows], "forecasting")
    result = forecast_frame(frame, body.horizon, body.level, body.value)
    return ForecastResponse(
        revenue=result["revenue"],
        roas=result["roas"],
        summary=result["summary"],
        validation=validation,
    )


@app.post("/api/simulate", response_model=SimulationResponse)
@limiter.limit("30/minute")
def simulate(request: Request, body: SimulationRequest) -> SimulationResponse:
    """Reforecast channel revenue after planned media budget changes."""
    frame, validation = _validated_frame([row.model_dump() for row in body.rows], "simulation")
    result = simulate_budgets(frame, body.horizon, body.budgets)
    return SimulationResponse(
        channels=result["channels"],
        totals=result["totals"],
        validation=validation,
        roas_decomposition=result.get("roas_decomposition", []),
    )


@app.post("/api/spend-curve")
def spend_curve(request: dict) -> dict:
    """Return channel-level spend response curve and saturation estimate."""
    rows = request.get("rows") or []
    frame, _ = _validated_frame(rows, "spend curve")
    channel = str(request.get("channel") or "Google Ads")
    horizon = int(request.get("horizon") or 30)
    current_budget = float(request.get("current_budget") or request.get("currentBudget") or 0)
    return compute_spend_response_curve(frame, channel, horizon, current_budget)


@app.post("/api/anomalies")
def get_anomalies(request: dict) -> dict:
    """Detect performance anomalies and structural trend breaks."""
    rows = request.get("rows") or []
    frame, _ = _validated_frame(rows, "anomaly detection")
    anomalies = [item.to_dict() for item in detect_anomalies(frame)]
    trend_breaks = compute_trend_breaks(frame)
    driver_evidence = compute_driver_evidence(frame)
    causal_estimates = estimate_causal_effects(frame, anomalies + trend_breaks)
    return {
        "anomalies": anomalies,
        "trendBreaks": trend_breaks,
        "driverEvidence": driver_evidence,
        "causalEstimates": causal_estimates,
    }


@app.post("/api/decision-support", response_model=DecisionSupportResponse)
@limiter.limit("30/minute")
def decision_support(request: Request, body: DecisionSupportRequest) -> DecisionSupportResponse:
    """Return optimizer, what-if, risk, opportunity and health analytics."""
    frame, validation = _validated_frame([row.model_dump() for row in body.rows], "decision support")
    result = build_decision_support(
        frame=frame,
        horizon=body.horizon,
        budgets=body.budgets,
        target_revenue=body.targetRevenue,
        target_roas=body.targetRoas,
        scenarios=body.scenarios,
    )
    return DecisionSupportResponse(**result, validation=validation)


@app.post("/api/insights", response_model=InsightsResponse)
@limiter.limit("30/minute")
async def insights(request: Request, body: InsightsRequest) -> InsightsResponse:
    """Turn forecast and performance summaries into executive recommendations."""
    return await generate_gemini_insights(body.summary)


@app.post("/api/train", response_model=TrainResponse)
def train(
    request: TrainRequest,
    x_training_admin_token: str | None = Header(default=None, alias="X-Training-Admin-Token"),
) -> TrainResponse:
    """Train and persist an evaluator-safe model artifact from uploaded rows."""
    _authorized_training_token(x_training_admin_token)
    model_path = _safe_model_path(request.modelPath)
    frame, validation = _validated_frame([row.model_dump() for row in request.rows], "training")
    bundle = train_evaluator_model(frame)
    model_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(bundle, model_path)
    return TrainResponse(
        modelPath=str(model_path.relative_to(PROJECT_ROOT)),
        modelType=bundle["model_type"],
        trainingRows=validation.validRows,
        message="Evaluator artifact trained and persisted",
    )
