from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import joblib
import numpy as np
import pandas as pd

from .data_preprocessing import aggregate_daily, feature_frame, filter_frame, future_features
from .schemas import (
    FeatureImportance,
    ForecastDiagnostics,
    ForecastPoint,
    ForecastSummary,
    SimChannelResult,
    SimulationTotals,
)
from .utils import DEFAULT_MODEL_PATH, ensure_dir, pct_change, round_money


try:
    from xgboost import XGBRegressor

    XGBOOST_AVAILABLE = True
except Exception:  # pragma: no cover - exercised only when dependency is unavailable
    from sklearn.ensemble import GradientBoostingRegressor

    XGBRegressor = None
    XGBOOST_AVAILABLE = False


CHANNELS = ["Google Ads", "Meta Ads", "Microsoft Ads"]


@dataclass
class TargetModel:
    model: Any
    residual_std: float
    feature_columns: List[str]
    model_type: str


def _model_type() -> str:
    return "xgboost" if XGBOOST_AVAILABLE else "sklearn_gradient_boosting_fallback"


def _new_model() -> Any:
    if XGBOOST_AVAILABLE:
        return XGBRegressor(
            objective="reg:squarederror",
            n_estimators=140,
            max_depth=4,
            learning_rate=0.06,
            subsample=0.9,
            colsample_bytree=0.9,
            reg_lambda=1.0,
            random_state=42,
            n_jobs=1,
        )

    return GradientBoostingRegressor(
        n_estimators=140,
        learning_rate=0.06,
        max_depth=3,
        random_state=42,
    )


def _fit_target(daily: pd.DataFrame, target: str) -> Optional[TargetModel]:
    X, y = feature_frame(daily, target)
    if len(X) < 10 or y.nunique() <= 1:
        return None

    model = _new_model()
    model.fit(X, y)
    preds = model.predict(X)
    residuals = y.to_numpy(dtype=float) - np.asarray(preds, dtype=float)
    residual_std = float(np.std(residuals, ddof=1)) if len(residuals) > 1 else float(np.std(residuals))
    if not np.isfinite(residual_std):
        residual_std = 0.0
    return TargetModel(
        model=model,
        residual_std=max(residual_std, float(np.mean(np.abs(y))) * 0.04, 1e-6),
        feature_columns=list(X.columns),
        model_type=_model_type(),
    )


def _target_quality(daily: pd.DataFrame, target: str, trained: Optional[TargetModel]) -> tuple[float, float]:
    if trained is None:
        return 0.0, 0.0
    X, y = feature_frame(daily, target)
    if X.empty:
        return 0.0, 0.0
    preds = np.asarray(trained.model.predict(X[trained.feature_columns]), dtype=float)
    actual = y.to_numpy(dtype=float)
    denom = np.maximum(np.abs(actual), 1.0)
    mape = float(np.mean(np.abs(actual - preds) / denom) * 100)
    lower = preds - (1.96 * trained.residual_std)
    upper = preds + (1.96 * trained.residual_std)
    coverage = float(np.mean((actual >= lower) & (actual <= upper)) * 100)
    return round_money(mape), round_money(coverage)


def _feature_importance(trained: Optional[TargetModel], limit: int = 6) -> List[FeatureImportance]:
    if trained is None or not hasattr(trained.model, "feature_importances_"):
        return []
    importances = np.asarray(trained.model.feature_importances_, dtype=float)
    total = float(importances.sum()) or 1.0
    ranked = sorted(
        zip(trained.feature_columns, importances / total),
        key=lambda item: item[1],
        reverse=True,
    )[:limit]
    return [FeatureImportance(feature=name, importance=round_money(score * 100)) for name, score in ranked]


def forecast_diagnostics(
    daily: pd.DataFrame,
    revenue_model: Optional[TargetModel],
    roas_model: Optional[TargetModel],
) -> Optional[ForecastDiagnostics]:
    if daily.empty:
        return None
    revenue_mape, revenue_coverage = _target_quality(daily, "revenue", revenue_model)
    roas_mape, roas_coverage = _target_quality(daily, "roas", roas_model)
    return ForecastDiagnostics(
        revenueFitMapePct=revenue_mape,
        roasFitMapePct=roas_mape,
        revenueIntervalCoveragePct=revenue_coverage,
        roasIntervalCoveragePct=roas_coverage,
        trainingDays=int(len(daily)),
        topRevenueFeatures=_feature_importance(revenue_model),
        topRoasFeatures=_feature_importance(roas_model),
    )


def train_model_bundle(frame: pd.DataFrame, model_path: str | Path = DEFAULT_MODEL_PATH) -> Dict[str, Any]:
    daily = aggregate_daily(frame)
    revenue_model = _fit_target(daily, "revenue")
    roas_model = _fit_target(daily, "roas")
    bundle = {
        "model_type": _model_type(),
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "training_rows": int(len(frame)),
        "revenue": revenue_model,
        "roas": roas_model,
    }
    path = Path(model_path)
    ensure_dir(path.parent)
    joblib.dump(bundle, path)
    return bundle


def load_model_bundle(model_path: str | Path = DEFAULT_MODEL_PATH) -> Optional[Dict[str, Any]]:
    path = Path(model_path)
    if not path.exists():
        return None
    try:
        return joblib.load(path)
    except Exception:
        return None


def _recent_mean(values: Iterable[float], default: float = 0.0) -> float:
    vals = [float(v) for v in values if np.isfinite(float(v))]
    return float(np.mean(vals)) if vals else default


def _project_exog(history: pd.DataFrame, future_date: pd.Timestamp, forced_daily_spend: Optional[float] = None) -> dict:
    recent = history.tail(min(28, len(history))).copy()
    if recent.empty:
        base = {"spend": 0.0, "clicks": 0.0, "impressions": 0.0, "conversions": 0.0}
    else:
        base = {
            "spend": _recent_mean(recent["spend"]),
            "clicks": _recent_mean(recent["clicks"]),
            "impressions": _recent_mean(recent["impressions"]),
            "conversions": _recent_mean(recent["conversions"]),
        }

    dow_rows = recent[pd.to_datetime(recent["date"]).dt.dayofweek == future_date.dayofweek] if not recent.empty else recent
    dow_spend = _recent_mean(dow_rows["spend"], base["spend"]) if not dow_rows.empty else base["spend"]
    seasonality = dow_spend / base["spend"] if base["spend"] > 0 else 1.0

    projected = {key: max(0.0, value * seasonality) for key, value in base.items()}
    if forced_daily_spend is not None:
        baseline_spend = projected["spend"] if projected["spend"] > 0 else base["spend"]
        ratio = forced_daily_spend / baseline_spend if baseline_spend > 0 else 1.0
        projected["spend"] = max(0.0, forced_daily_spend)
        projected["clicks"] = max(0.0, projected["clicks"] * ratio)
        projected["impressions"] = max(0.0, projected["impressions"] * ratio)
        projected["conversions"] = max(0.0, projected["conversions"] * ratio)
    return projected


def _historical_points(daily: pd.DataFrame, target: str) -> List[ForecastPoint]:
    return [
        ForecastPoint(
            date=str(row.date),
            value=round_money(getattr(row, target)),
            lower=round_money(getattr(row, target)),
            upper=round_money(getattr(row, target)),
            historical=True,
        )
        for row in daily.itertuples(index=False)
    ]


def _fallback_forecast(daily: pd.DataFrame, horizon: int, target: str, forced_daily_spend: Optional[float] = None) -> List[ForecastPoint]:
    points = _historical_points(daily, target)
    if daily.empty:
        return points

    recent = daily.tail(min(28, len(daily)))
    expected = _recent_mean(recent[target])
    std = float(np.std(recent[target], ddof=1)) if len(recent) > 1 else expected * 0.2
    last_date = pd.to_datetime(daily["date"].iloc[-1])
    history = daily.copy()
    for step in range(1, horizon + 1):
        future_date = last_date + pd.Timedelta(days=step)
        exog = _project_exog(history, future_date, forced_daily_spend)
        if target == "revenue" and forced_daily_spend is not None:
            recent_roas = _recent_mean(recent["roas"], 1.0)
            pred = exog["spend"] * recent_roas
        elif target == "roas" and forced_daily_spend is not None:
            pred = expected * (0.98 + min(0.12, step / 900))
        else:
            pred = expected
        margin = 1.96 * max(std, abs(pred) * 0.08) * np.sqrt(1 + step / 30)
        points.append(
            ForecastPoint(
                date=future_date.strftime("%Y-%m-%d"),
                value=round_money(max(0.0, pred)),
                lower=round_money(max(0.0, pred - margin)),
                upper=round_money(max(0.0, pred + margin)),
            )
        )
        new_row = {
            "date": future_date.strftime("%Y-%m-%d"),
            "spend": exog["spend"],
            "clicks": exog["clicks"],
            "impressions": exog["impressions"],
            "conversions": exog["conversions"],
            "revenue": pred if target == "revenue" else exog["spend"] * pred,
            "roas": pred if target == "roas" else (pred / exog["spend"] if exog["spend"] > 0 else 0.0),
        }
        history = pd.concat([history, pd.DataFrame([new_row])], ignore_index=True)
    return points


def _forecast_target(
    daily: pd.DataFrame,
    horizon: int,
    target: str,
    forced_daily_spend: Optional[float] = None,
    target_model: Optional[TargetModel] = None,
) -> List[ForecastPoint]:
    if daily.empty:
        return []

    trained = target_model or _fit_target(daily, target)
    if trained is None:
        return _fallback_forecast(daily, horizon, target, forced_daily_spend)

    points = _historical_points(daily, target)
    history = daily.copy().sort_values("date").reset_index(drop=True)
    last_date = pd.to_datetime(history["date"].iloc[-1])

    for step in range(1, horizon + 1):
        future_date = last_date + pd.Timedelta(days=step)
        exog = _project_exog(history, future_date, forced_daily_spend)
        X_future = future_features(history, target, future_date, exog)[trained.feature_columns]
        pred = float(trained.model.predict(X_future)[0])
        pred = max(0.0, pred)
        margin = 1.96 * max(trained.residual_std, pred * 0.06) * np.sqrt(1 + step / 30)
        lower = max(0.0, pred - margin)
        upper = pred + margin

        points.append(
            ForecastPoint(
                date=future_date.strftime("%Y-%m-%d"),
                value=round_money(pred),
                lower=round_money(lower),
                upper=round_money(upper),
            )
        )

        history = pd.concat(
            [
                history,
                pd.DataFrame(
                    [
                        {
                            "date": future_date.strftime("%Y-%m-%d"),
                            "spend": exog["spend"],
                            "clicks": exog["clicks"],
                            "impressions": exog["impressions"],
                            "conversions": exog["conversions"],
                            "revenue": pred if target == "revenue" else exog["spend"] * pred,
                            "roas": pred if target == "roas" else (pred / exog["spend"] if exog["spend"] > 0 else 0.0),
                        }
                    ]
                ),
            ],
            ignore_index=True,
        )

    return points


def forecast_frame(
    frame: pd.DataFrame,
    horizon: int,
    level: str = "overall",
    value: Optional[str] = None,
    model_bundle: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    segment = filter_frame(frame, level, value)
    daily = aggregate_daily(segment)
    revenue_model = model_bundle.get("revenue") if model_bundle else None
    roas_model = model_bundle.get("roas") if model_bundle else None
    if revenue_model is None:
        revenue_model = _fit_target(daily, "revenue")
    if roas_model is None:
        roas_model = _fit_target(daily, "roas")
    revenue = _forecast_target(daily, horizon, "revenue", target_model=revenue_model)
    roas = _forecast_target(daily, horizon, "roas", target_model=roas_model)

    future_revenue = [point for point in revenue if not point.historical]
    future_roas = [point for point in roas if not point.historical]
    expected_revenue = sum(point.value for point in future_revenue)
    lower_revenue = sum(point.lower for point in future_revenue)
    upper_revenue = sum(point.upper for point in future_revenue)
    avg_roas = sum(point.value for point in future_roas) / len(future_roas) if future_roas else 0.0
    model_type = (model_bundle or {}).get("model_type") or _model_type()

    return {
        "revenue": revenue,
        "roas": roas,
        "summary": ForecastSummary(
            expectedRevenue=round_money(expected_revenue),
            lowerRevenue=round_money(lower_revenue),
            upperRevenue=round_money(upper_revenue),
            avgRoas=round_money(avg_roas),
            horizonDays=horizon,
            level=level,
            value=value,
            modelType=model_type,
            diagnostics=forecast_diagnostics(daily, revenue_model, roas_model),
        ),
    }


def simulate_budgets(frame: pd.DataFrame, horizon: int, budgets: Dict[str, float]) -> Dict[str, Any]:
    results: List[SimChannelResult] = []
    available_channels = list(dict.fromkeys(CHANNELS + sorted(frame["channel"].dropna().unique().tolist()))) if not frame.empty else CHANNELS

    for channel in available_channels:
        channel_frame = frame[frame["channel"] == channel].copy()
        daily = aggregate_daily(channel_frame)
        if daily.empty:
            new_total = float(budgets.get(channel, 0.0))
            results.append(
                SimChannelResult(
                    channel=channel,
                    horizonDays=horizon,
                    baselineDailySpend=0,
                    newDailySpend=new_total / horizon if horizon else 0,
                    baselineTotalSpend=0,
                    newTotalSpend=new_total,
                    baselineRevenue=0,
                    projectedRevenue=0,
                    projectedRevenueLower=0,
                    projectedRevenueUpper=0,
                    baselineRoas=0,
                    projectedRoas=0,
                    daily=[],
                )
            )
            continue

        lookback = min(horizon, len(daily))
        recent = daily.tail(max(1, lookback))
        baseline_daily_spend = float(recent["spend"].mean())
        baseline_daily_revenue = float(recent["revenue"].mean())
        baseline_total_spend = baseline_daily_spend * horizon
        baseline_revenue = baseline_daily_revenue * horizon
        baseline_roas = baseline_revenue / baseline_total_spend if baseline_total_spend > 0 else 0.0
        new_total_spend = float(budgets.get(channel, baseline_total_spend))
        new_daily_spend = new_total_spend / horizon if horizon else 0.0

        revenue_points = _forecast_target(daily, horizon, "revenue", forced_daily_spend=new_daily_spend)
        future = [point for point in revenue_points if not point.historical]
        projected_revenue = sum(point.value for point in future)
        lower = sum(point.lower for point in future)
        upper = sum(point.upper for point in future)
        projected_roas = projected_revenue / new_total_spend if new_total_spend > 0 else 0.0

        results.append(
            SimChannelResult(
                channel=channel,
                horizonDays=horizon,
                baselineDailySpend=round_money(baseline_daily_spend),
                newDailySpend=round_money(new_daily_spend),
                baselineTotalSpend=round_money(baseline_total_spend),
                newTotalSpend=round_money(new_total_spend),
                baselineRevenue=round_money(baseline_revenue),
                projectedRevenue=round_money(projected_revenue),
                projectedRevenueLower=round_money(lower),
                projectedRevenueUpper=round_money(upper),
                baselineRoas=round_money(baseline_roas),
                projectedRoas=round_money(projected_roas),
                daily=future,
            )
        )

    total_new_spend = sum(item.newTotalSpend for item in results)
    total_base_spend = sum(item.baselineTotalSpend for item in results)
    total_projected = sum(item.projectedRevenue for item in results)
    total_lower = sum(item.projectedRevenueLower for item in results)
    total_upper = sum(item.projectedRevenueUpper for item in results)
    total_baseline = sum(item.baselineRevenue for item in results)
    projected_roas = total_projected / total_new_spend if total_new_spend > 0 else 0.0
    baseline_roas = total_baseline / total_base_spend if total_base_spend > 0 else 0.0

    return {
        "channels": results,
        "totals": SimulationTotals(
            totalNewSpend=round_money(total_new_spend),
            totalBaseSpend=round_money(total_base_spend),
            totalProjectedRevenue=round_money(total_projected),
            totalProjectedRevenueLower=round_money(total_lower),
            totalProjectedRevenueUpper=round_money(total_upper),
            totalBaselineRevenue=round_money(total_baseline),
            projectedRoas=round_money(projected_roas),
            baselineRoas=round_money(baseline_roas),
            revenueChangePct=round_money(pct_change(total_projected, total_baseline)),
            roasChangePct=round_money(pct_change(projected_roas, baseline_roas)),
        ),
    }


def aggregate_prediction_rows(frame: pd.DataFrame, model_bundle: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    output: List[Dict[str, Any]] = []
    segment_specs: list[tuple[str, Optional[str]]] = [("overall", None)]
    for level, column in [("channel", "channel"), ("campaign_type", "campaign_type"), ("campaign", "campaign_name")]:
        for value in sorted(frame[column].dropna().unique().tolist()):
            segment_specs.append((level, str(value)))

    for horizon in (30, 60, 90):
        for level, value in segment_specs:
            segment_bundle = model_bundle if level == "overall" else None
            forecast = forecast_frame(frame, horizon, level, value, model_bundle=segment_bundle)
            summary: ForecastSummary = forecast["summary"]
            output.append(
                {
                    "level": level,
                    "segment": value or "all",
                    "horizon_days": horizon,
                    "expected_revenue": summary.expectedRevenue,
                    "lower_revenue": summary.lowerRevenue,
                    "upper_revenue": summary.upperRevenue,
                    "expected_roas": summary.avgRoas,
                    "model_type": summary.modelType,
                }
            )
    return output
