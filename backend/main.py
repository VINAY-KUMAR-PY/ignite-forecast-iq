from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .data_preprocessing import validate_records
from .forecasting import forecast_frame, simulate_budgets, train_model_bundle
from .gemini import generate_gemini_insights
from .schemas import (
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


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "forecastiq-api"}


@app.post("/api/validate", response_model=ValidationResponse)
def validate_data(request: ValidationRequest) -> ValidationResponse:
    _, validation = validate_records(request.rows)
    return validation


@app.post("/api/forecast", response_model=ForecastResponse)
def forecast(request: ForecastRequest) -> ForecastResponse:
    frame, validation = validate_records([row.model_dump() for row in request.rows])
    if frame.empty:
        raise HTTPException(status_code=422, detail="No valid rows available for forecasting")
    result = forecast_frame(frame, request.horizon, request.level, request.value)
    return ForecastResponse(
        revenue=result["revenue"],
        roas=result["roas"],
        summary=result["summary"],
        validation=validation,
    )


@app.post("/api/simulate", response_model=SimulationResponse)
def simulate(request: SimulationRequest) -> SimulationResponse:
    frame, validation = validate_records([row.model_dump() for row in request.rows])
    if frame.empty:
        raise HTTPException(status_code=422, detail="No valid rows available for simulation")
    result = simulate_budgets(frame, request.horizon, request.budgets)
    return SimulationResponse(channels=result["channels"], totals=result["totals"], validation=validation)


@app.post("/api/insights", response_model=InsightsResponse)
async def insights(request: InsightsRequest) -> InsightsResponse:
    return await generate_gemini_insights(request.summary)


@app.post("/api/train", response_model=TrainResponse)
def train(request: TrainRequest) -> TrainResponse:
    frame, validation = validate_records([row.model_dump() for row in request.rows])
    if frame.empty:
        raise HTTPException(status_code=422, detail="No valid rows available for training")
    bundle = train_model_bundle(frame, request.modelPath)
    return TrainResponse(
        modelPath=request.modelPath,
        modelType=bundle["model_type"],
        trainingRows=validation.validRows,
        message="Model bundle trained and persisted",
    )
