from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from time import perf_counter

import joblib
from fastapi import FastAPI, Header, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from .data_preprocessing import validate_records
from .decision_support import compute_driver_evidence, estimate_causal_effects
from .anomaly import compute_trend_breaks, detect_anomalies
from .forecasting import forecast_frame
from .gemini import generate_gemini_insights
from .lightweight_api import (
    aggregate_channel_summaries,
    build_lightweight_decision_support,
    build_lightweight_simulation,
    build_lightweight_spend_curve,
    validate_budget_channels,
)
from .train import train_evaluator_model
from .schemas import (
    AnomalyRequest,
    DecisionSupportRequest,
    DecisionSupportResponse,
    ForecastRequest,
    ForecastResponse,
    InsightsRequest,
    InsightsResponse,
    SimulationRequest,
    SimulationResponse,
    SpendCurveRequest,
    TrainRequest,
    TrainResponse,
    ValidationRequest,
    ValidationIssue,
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
LIGHTWEIGHT_ROW_CAP = 1000

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


def _validate_budget_channels(frame, budgets: dict[str, float], operation: str) -> None:
    """Reject planned budgets for channels absent from the uploaded dataset."""
    if not budgets:
        return
    observed = {
        str(channel).strip().casefold()
        for channel in frame.get("channel", [])
        if str(channel).strip()
    }
    unknown = [channel for channel in budgets if str(channel).strip().casefold() not in observed]
    if unknown:
        raise HTTPException(
            status_code=422,
            detail=(
                f"{operation} budget channel '{unknown[0]}' is not present in the uploaded data. "
                "Upload rows for that channel or remove the budget override."
            ),
        )


def _lightweight_bundle(rows, operation: str):
    """Aggregate frontend simulator rows without pandas/model work."""
    bundle = aggregate_channel_summaries(rows)
    if len(rows) > LIGHTWEIGHT_ROW_CAP:
        rows.clear()
        logger.info(
            "%s request exceeded %s rows; raw rows discarded after aggregation",
            operation,
            LIGHTWEIGHT_ROW_CAP,
        )
    return bundle


def _lightweight_validation(bundle) -> ValidationResponse:
    return ValidationResponse(
        rows=[],
        issues=[
            ValidationIssue(
                type="info",
                row=0,
                message=(
                    "Frontend simulator endpoints used memory-safe channel aggregates; "
                    "raw validated rows were discarded after request parsing."
                ),
            )
        ],
        totalRows=bundle.row_count,
        validRows=bundle.row_count,
    )


def _log_lightweight_api(operation: str, row_count: int, aggregate_count: int, started: float) -> None:
    logger.info(
        "%s memory-safe path used: row_count=%s aggregate_count=%s elapsed_ms=%.1f",
        operation,
        row_count,
        aggregate_count,
        (perf_counter() - started) * 1000,
    )


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
    started = perf_counter()
    bundle = _lightweight_bundle(body.rows, "simulation")
    try:
        validate_budget_channels(bundle, body.budgets, "Simulation")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    result = build_lightweight_simulation(bundle, body.horizon, body.budgets)
    _log_lightweight_api("simulation", bundle.row_count, bundle.aggregate_count, started)
    return SimulationResponse(
        channels=result["channels"],
        totals=result["totals"],
        validation=_lightweight_validation(bundle),
        roas_decomposition=result.get("roas_decomposition", []),
    )


@app.post("/api/spend-curve")
@limiter.limit("30/minute")
def spend_curve(request: Request, body: SpendCurveRequest) -> dict:
    """Return channel-level spend response curve and saturation estimate."""
    started = perf_counter()
    bundle = _lightweight_bundle(body.rows, "spend curve")
    result = build_lightweight_spend_curve(bundle, body.channel, int(body.horizon), float(body.current_budget))
    _log_lightweight_api("spend_curve", bundle.row_count, bundle.aggregate_count, started)
    return result


@app.post("/api/anomalies")
@limiter.limit("30/minute")
def get_anomalies(request: Request, body: AnomalyRequest) -> dict:
    """Detect performance anomalies and structural trend breaks."""
    frame, _ = _validated_frame([row.model_dump() for row in body.rows], "anomaly detection")
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
    started = perf_counter()
    bundle = _lightweight_bundle(body.rows, "decision support")
    try:
        validate_budget_channels(bundle, body.budgets, "Decision support")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    result = build_lightweight_decision_support(
        bundle=bundle,
        horizon=body.horizon,
        budgets=body.budgets,
        target_revenue=body.targetRevenue,
        target_roas=body.targetRoas,
        scenarios=body.scenarios,
    )
    _log_lightweight_api("decision_support", bundle.row_count, bundle.aggregate_count, started)
    return DecisionSupportResponse(**result, validation=_lightweight_validation(bundle))


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
