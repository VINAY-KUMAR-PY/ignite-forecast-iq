"""Revenue, ROAS and budget simulation models for ForecastIQ."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import logging
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import joblib
import numpy as np
import pandas as pd

from .data_preprocessing import aggregate_daily, feature_frame, filter_frame, future_features
from .schemas import (
    AccuracyMetrics,
    ForecastContribution,
    FeatureImportance,
    ForecastBusinessBrief,
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
logger = logging.getLogger(__name__)
HORIZON_CONFIGS = {
    30: {"n_estimators": 200, "max_depth": 4, "learning_rate": 0.05, "subsample": 0.8, "colsample_bytree": 0.8},
    60: {"n_estimators": 100, "max_depth": 3, "learning_rate": 0.05},
    90: {"n_estimators": 80, "max_depth": 3, "learning_rate": 0.04},
}


@dataclass
class TargetModel:
    model: Any
    residual_std: float
    feature_columns: List[str]
    model_type: str


def _model_type() -> str:
    return "xgboost" if XGBOOST_AVAILABLE else "sklearn_gradient_boosting_fallback"


def _new_model(horizon: int = 30) -> Any:
    config = HORIZON_CONFIGS.get(int(horizon), HORIZON_CONFIGS[30])
    if XGBOOST_AVAILABLE:
        return XGBRegressor(
            objective="reg:squarederror",
            n_estimators=config["n_estimators"],
            max_depth=config["max_depth"],
            learning_rate=config["learning_rate"],
            subsample=config.get("subsample", 0.9),
            colsample_bytree=config.get("colsample_bytree", 0.9),
            reg_lambda=1.0,
            random_state=42,
            n_jobs=1,
        )

    return GradientBoostingRegressor(
        n_estimators=config["n_estimators"],
        learning_rate=config["learning_rate"],
        max_depth=config["max_depth"],
        random_state=42,
    )


def _fit_target(daily: pd.DataFrame, target: str, horizon: int = 30) -> Optional[TargetModel]:
    training_daily = daily.copy()
    training_target = target
    if target == "revenue" and horizon in {60, 90}:
        training_target = f"revenue_horizon_{horizon}"
        training_daily[training_target] = (
            training_daily["revenue"]
            .shift(-1)
            .rolling(horizon, min_periods=max(14, horizon // 3))
            .sum()
            .shift(-(horizon - 1))
        )
    X, y = feature_frame(training_daily, training_target)
    if len(X) < 10 or y.nunique() <= 1:
        return None

    model = _new_model(horizon)
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


def _target_quality(daily: pd.DataFrame, target: str, trained: Optional[TargetModel]) -> tuple[AccuracyMetrics, float]:
    if trained is None:
        return _empty_accuracy(), 0.0
    X, y = feature_frame(daily, target)
    if X.empty:
        return _empty_accuracy(), 0.0
    preds = np.asarray(trained.model.predict(X[trained.feature_columns]), dtype=float)
    actual = y.to_numpy(dtype=float)
    errors = actual - preds
    denom = np.maximum(np.abs(actual), 1.0)
    mae = float(np.mean(np.abs(errors)))
    rmse = float(np.sqrt(np.mean(errors**2)))
    mape = float(np.mean(np.abs(errors) / denom) * 100)
    ss_res = float(np.sum(errors**2))
    ss_tot = float(np.sum((actual - np.mean(actual)) ** 2))
    r2 = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0.0
    lower = preds - (1.96 * trained.residual_std)
    upper = preds + (1.96 * trained.residual_std)
    coverage = float(np.mean((actual >= lower) & (actual <= upper)) * 100)
    return (
        AccuracyMetrics(
            mae=round_money(mae),
            rmse=round_money(rmse),
            mapePct=round_money(mape),
            r2Score=round_money(r2),
        ),
        round_money(coverage),
    )


def _empty_accuracy() -> AccuracyMetrics:
    return AccuracyMetrics(mae=0.0, rmse=0.0, mapePct=0.0, r2Score=0.0)


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
    return [
        FeatureImportance(feature=name, label=_feature_label(name), importance=round_money(score * 100))
        for name, score in ranked
    ]


def _shap_importance(daily: pd.DataFrame, target: str, trained: Optional[TargetModel], limit: int = 10) -> list[dict[str, Any]]:
    """Return SHAP attribution or a deterministic permutation-importance fallback."""
    if trained is None or daily.empty:
        return []

    X, y = feature_frame(daily, target)
    if X.empty:
        return []
    sample = X[trained.feature_columns].tail(min(50, len(X))).astype(float)
    sample_target = y.tail(len(sample)).astype(float)
    if sample.empty or sample_target.empty:
        return []

    def attribution_item(index: int, importance: float, direction: str) -> dict[str, Any]:
        feature = trained.feature_columns[index]
        rounded_importance = round(float(importance), 6)
        return {
            "feature": feature,
            "shap_value": rounded_importance,
            "importance": rounded_importance,
            "label": _feature_label(feature),
            "direction": direction,
        }

    def permutation_fallback() -> list[dict[str, Any]]:
        try:
            from sklearn.inspection import permutation_importance

            result = permutation_importance(
                trained.model,
                sample,
                sample_target,
                n_repeats=5,
                random_state=42,
                n_jobs=1,
            )
            importances = np.asarray(result.importances_mean, dtype=float)
            ranked = np.argsort(importances)[::-1][:limit]
            items: list[dict[str, Any]] = []
            for index in ranked:
                importance = importances[int(index)]
                if not np.isfinite(importance) or importance <= 0:
                    continue
                feature_values = sample.iloc[:, int(index)].to_numpy(dtype=float)
                direction = "positive"
                if np.std(feature_values) > 1e-9 and np.std(sample_target) > 1e-9:
                    correlation = float(np.corrcoef(feature_values, sample_target)[0, 1])
                    if np.isfinite(correlation) and correlation < 0:
                        direction = "negative"
                items.append(attribution_item(int(index), importance, direction))
            return items
        except Exception as exc:
            logger.info("Permutation forecast attribution unavailable: %s", exc)
            return []

    try:
        import shap

        explainer = shap.TreeExplainer(trained.model)
        shap_values = explainer.shap_values(sample)
        if isinstance(shap_values, list):
            shap_values = shap_values[0]
        values = np.asarray(shap_values, dtype=float)
        if values.ndim == 3:
            values = values[:, :, 0]
        if values.ndim != 2 or values.shape[1] != len(trained.feature_columns):
            return []

        global_shap = np.abs(values).mean(axis=0)
        directions = values.mean(axis=0)
        ranked = np.argsort(global_shap)[::-1][:limit]
        return [
            attribution_item(
                int(index),
                global_shap[int(index)],
                "positive" if directions[int(index)] >= 0 else "negative",
            )
            for index in ranked
            if np.isfinite(global_shap[int(index)]) and global_shap[int(index)] > 0
        ]
    except (ImportError, ModuleNotFoundError):
        logger.info("SHAP is unavailable; using permutation importance for forecast attribution")
        return permutation_fallback()
    except Exception as exc:
        logger.info("SHAP forecast attribution failed: %s; using permutation importance", exc)
        return permutation_fallback()


def _feature_label(feature: str) -> str:
    labels = {
        "spend": "current spend",
        "clicks": "click volume",
        "impressions": "impression volume",
        "conversions": "conversion volume",
        "dow": "day-of-week pattern",
        "month": "monthly seasonality",
        "sin_year": "annual seasonality",
        "cos_year": "annual seasonality",
        "is_holiday_week": "major retail holiday week",
        "is_q4": "Q4 retail season",
        "month_sin": "monthly cycle",
        "month_cos": "monthly cycle",
        "week_of_year_sin": "weekly annual cycle",
        "week_of_year_cos": "weekly annual cycle",
        "days_to_black_friday": "Black Friday proximity",
        "trend": "time trend",
        "spend_roll_7": "7-day average spend",
        "spend_roll_28": "28-day average spend",
        "spend_lag_1": "prior-day spend",
        "spend_lag_7": "same weekday spend",
        "spend_lag_14": "two-week spend lag",
    }
    if feature in labels:
        return labels[feature]
    if "_lag_" in feature:
        target, lag = feature.split("_lag_")
        return f"{target.upper()} {lag}-day lag"
    if "_roll_" in feature:
        target, window = feature.split("_roll_")
        return f"{window}-day average {target.upper()}"
    return feature.replace("_", " ")


def _explain_features(target: str, features: List[FeatureImportance]) -> str:
    if not features:
        return f"The {target} model did not expose reliable feature importance for this segment."
    top = features[:3]
    driver_text = ", ".join(f"{item.label or item.feature} ({item.importance:.1f}%)" for item in top)
    return (
        f"The {target} forecast is primarily shaped by {driver_text}. "
        "These drivers combine current media intensity, lagged performance and seasonal signals."
    )


def _impact_phrase(direction: str, label: str, impact: float, target: str) -> str:
    movement = "raises" if direction == "positive" else "pulls down"
    unit = "forecast revenue" if target == "revenue" else "forecast ROAS"
    formatted = f"{impact:,.0f}" if target == "revenue" else f"{impact:.2f}x"
    return f"{label} {movement} the local {unit} by about {formatted} versus a typical historical value."


def _local_permutation_explanations(
    daily: pd.DataFrame,
    trained: Optional[TargetModel],
    target: str,
    limit_per_direction: int = 3,
) -> tuple[List[ForecastContribution], str]:
    """Estimate local driver impact by replacing one forecast feature with its historical median."""
    if trained is None or daily.empty:
        return [], "Local forecast explanations are unavailable because this segment used fallback forecasting."

    try:
        X_train, _ = feature_frame(daily, target)
        if X_train.empty:
            return [], "Local forecast explanations need more valid history for this segment."

        history = daily.copy().sort_values("date").reset_index(drop=True)
        future_date = pd.to_datetime(history["date"].iloc[-1]) + pd.Timedelta(days=1)
        exog = _project_exog(history, future_date)
        current = future_features(history, target, future_date, exog)[trained.feature_columns].astype(float)
        baseline_frame = X_train[trained.feature_columns]
        median_values = baseline_frame.median(numeric_only=True)
        lower_values = baseline_frame.quantile(0.25, numeric_only=True)
        upper_values = baseline_frame.quantile(0.75, numeric_only=True)
        base_prediction = float(trained.model.predict(current)[0])

        impacts: list[tuple[str, float]] = []
        for feature in trained.feature_columns:
            if feature not in current.columns:
                continue
            feature_impacts: list[float] = []
            for values in (median_values, lower_values, upper_values):
                replacement = float(values.get(feature, 0.0))
                mutated = current.copy()
                mutated.loc[:, feature] = replacement
                mutated_prediction = float(trained.model.predict(mutated)[0])
                impact = base_prediction - mutated_prediction
                if np.isfinite(impact):
                    feature_impacts.append(impact)
            if feature_impacts:
                strongest = max(feature_impacts, key=lambda value: abs(value))
                if abs(strongest) > 1e-6:
                    impacts.append((feature, strongest))

        positive = sorted((item for item in impacts if item[1] > 0), key=lambda item: item[1], reverse=True)[
            :limit_per_direction
        ]
        negative = sorted((item for item in impacts if item[1] < 0), key=lambda item: item[1])[
            :limit_per_direction
        ]

        contributions: List[ForecastContribution] = []
        for feature, impact in positive + negative:
            direction = "positive" if impact > 0 else "negative"
            label = _feature_label(feature)
            abs_impact = round_money(abs(impact))
            contributions.append(
                ForecastContribution(
                    feature=feature,
                    label=label,
                    direction=direction,
                    impact=abs_impact,
                    explanation=_impact_phrase(direction, label, abs_impact, target),
                )
            )

        if not contributions:
            return [], "No single feature materially changed the local forecast versus typical history."

        pos_count = sum(1 for item in contributions if item.direction == "positive")
        neg_count = sum(1 for item in contributions if item.direction == "negative")
        summary = (
            f"Permutation-baseline analysis found {pos_count} positive and {neg_count} negative local drivers. "
            "Each impact compares the current forecast feature row with that feature set to its historical median."
        )
        return contributions, summary
    except Exception as exc:
        logger.info("Local forecast explainability unavailable: %s", exc)
        return [], "Local forecast explanations are unavailable for this segment."


def _business_brief(
    daily: pd.DataFrame,
    future_revenue: List[ForecastPoint],
    future_roas: List[ForecastPoint],
    revenue_accuracy: AccuracyMetrics,
    roas_accuracy: AccuracyMetrics,
) -> ForecastBusinessBrief:
    recent = daily.tail(min(30, len(daily)))
    previous = daily.iloc[max(0, len(daily) - 60) : max(0, len(daily) - 30)]
    recent_revenue = float(recent["revenue"].sum()) if not recent.empty else 0.0
    previous_revenue = float(previous["revenue"].sum()) if not previous.empty else 0.0
    recent_spend = float(recent["spend"].sum()) if not recent.empty else 0.0
    previous_spend = float(previous["spend"].sum()) if not previous.empty else 0.0
    recent_roas = recent_revenue / recent_spend if recent_spend > 0 else 0.0
    previous_roas = previous_revenue / previous_spend if previous_spend > 0 else 0.0
    revenue_trend = pct_change(recent_revenue, previous_revenue)
    roas_trend = pct_change(recent_roas, previous_roas)
    expected_revenue = sum(point.value for point in future_revenue)
    lower_revenue = sum(point.lower for point in future_revenue)
    upper_revenue = sum(point.upper for point in future_revenue)
    avg_roas = sum(point.value for point in future_roas) / len(future_roas) if future_roas else 0.0
    interval_width_pct = ((upper_revenue - lower_revenue) / expected_revenue * 100) if expected_revenue > 0 else 0.0

    risks: List[str] = []
    opportunities: List[str] = []
    actions: List[str] = []

    if revenue_trend < -5:
        risks.append(f"Recent revenue is down {abs(revenue_trend):.1f}% versus the prior period.")
        actions.append("Audit declining campaigns before approving incremental media spend.")
    if roas_trend < -5:
        risks.append(f"Recent ROAS is down {abs(roas_trend):.1f}%, indicating possible efficiency pressure.")
        actions.append("Shift budget toward campaigns with stable conversion quality and stronger marginal ROAS.")
    if interval_width_pct > 35:
        risks.append("The confidence interval is wide, so leadership should plan with conservative and upside cases.")
        actions.append("Use the lower confidence bound for committed targets and the midpoint for stretch planning.")
    if revenue_accuracy.mapePct > 20 or roas_accuracy.mapePct > 20:
        risks.append("Model error is elevated for this segment; monitor actuals closely after launch.")

    if revenue_trend > 5:
        opportunities.append(f"Recent revenue is up {revenue_trend:.1f}%, creating a scaling opportunity.")
        actions.append("Test controlled budget expansion while tracking daily ROAS movement.")
    if roas_trend > 5:
        opportunities.append(f"Recent ROAS is up {roas_trend:.1f}%, suggesting improving media efficiency.")
    if interval_width_pct <= 25 and revenue_accuracy.mapePct <= 15:
        opportunities.append("Forecast uncertainty is contained enough for confident short-term planning.")

    if not risks:
        risks.append("No severe revenue or ROAS degradation is visible in the current forecast segment.")
    if not opportunities:
        opportunities.append("Use channel-level forecasts to find the strongest budget reallocation candidate.")
    if not actions:
        actions.append("Review forecast actuals weekly and re-run the simulator before budget approval.")

    summary = (
        f"The model projects {round_money(expected_revenue):,.0f} revenue with average ROAS of "
        f"{round_money(avg_roas):.2f}x. Recent revenue trend is {round_money(revenue_trend):.1f}% "
        f"and recent ROAS trend is {round_money(roas_trend):.1f}%."
    )
    return ForecastBusinessBrief(
        summary=summary,
        risks=risks[:4],
        opportunities=opportunities[:4],
        recommendedActions=actions[:4],
    )


def forecast_diagnostics(
    daily: pd.DataFrame,
    revenue_model: Optional[TargetModel],
    roas_model: Optional[TargetModel],
    future_revenue: List[ForecastPoint],
    future_roas: List[ForecastPoint],
) -> Optional[ForecastDiagnostics]:
    """Summarize in-sample model fit and feature drivers for explainability."""
    if daily.empty:
        return None
    revenue_accuracy, revenue_coverage = _target_quality(daily, "revenue", revenue_model)
    roas_accuracy, roas_coverage = _target_quality(daily, "roas", roas_model)
    revenue_features = _feature_importance(revenue_model)
    roas_features = _feature_importance(roas_model)
    local_drivers, local_summary = _local_permutation_explanations(daily, revenue_model, "revenue")
    return ForecastDiagnostics(
        revenueFitMapePct=revenue_accuracy.mapePct,
        roasFitMapePct=roas_accuracy.mapePct,
        revenueIntervalCoveragePct=revenue_coverage,
        roasIntervalCoveragePct=roas_coverage,
        trainingDays=int(len(daily)),
        topRevenueFeatures=revenue_features,
        topRoasFeatures=roas_features,
        revenueAccuracy=revenue_accuracy,
        roasAccuracy=roas_accuracy,
        revenueExplanation=_explain_features("revenue", revenue_features),
        roasExplanation=_explain_features("ROAS", roas_features),
        explainabilityMethod="permutation_baseline",
        shap_importance=_shap_importance(daily, "revenue", revenue_model),
        whyThisForecast=local_drivers,
        whyThisForecastSummary=local_summary,
        businessBrief=_business_brief(daily, future_revenue, future_roas, revenue_accuracy, roas_accuracy),
    )


def train_model_bundle(frame: pd.DataFrame, model_path: str | Path = DEFAULT_MODEL_PATH) -> Dict[str, Any]:
    """Train revenue and ROAS estimators and persist them as one bundle."""
    daily = aggregate_daily(frame)
    revenue_models = {horizon: _fit_target(daily, "revenue", horizon) for horizon in (30, 60, 90)}
    roas_model = _fit_target(daily, "roas")
    bundle = {
        "model_type": _model_type(),
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "training_rows": int(len(frame)),
        "revenue": revenue_models.get(30),
        "revenue_by_horizon": revenue_models,
        "roas": roas_model,
    }
    path = Path(model_path)
    ensure_dir(path.parent)
    joblib.dump(bundle, path)
    return bundle


def load_model_bundle(model_path: str | Path = DEFAULT_MODEL_PATH) -> Optional[Dict[str, Any]]:
    """Load a persisted model bundle, returning None when it is unavailable."""
    path = Path(model_path)
    if not path.exists():
        return None
    try:
        return joblib.load(path)
    except Exception as exc:
        logger.warning("Unable to load model bundle from %s: %s", path, exc)
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
    """Forecast revenue and ROAS for the requested segment and horizon."""
    segment = filter_frame(frame, level, value)
    daily = aggregate_daily(segment)
    revenue_model = None
    if model_bundle:
        revenue_by_horizon = model_bundle.get("revenue_by_horizon") or {}
        revenue_model = revenue_by_horizon.get(horizon) or revenue_by_horizon.get(str(horizon)) or model_bundle.get("revenue")
    roas_model = model_bundle.get("roas") if model_bundle else None
    if revenue_model is None:
        revenue_model = _fit_target(daily, "revenue", horizon)
    if roas_model is None:
        roas_model = _fit_target(daily, "roas")
    revenue = _forecast_target(daily, horizon, "revenue", target_model=revenue_model)
    roas = _forecast_target(daily, horizon, "roas", target_model=roas_model)

    future_revenue = [point for point in revenue if not point.historical]
    future_roas = [point for point in roas if not point.historical]
    expected_revenue = sum(point.value for point in future_revenue)
    lower_revenue = sum(point.lower for point in future_revenue)
    upper_revenue = sum(point.upper for point in future_revenue)
    projected_spend = (
        sum(
            _project_exog(daily, pd.to_datetime(daily["date"].iloc[-1]) + pd.Timedelta(days=step))["spend"]
            for step in range(1, horizon + 1)
        )
        if not daily.empty
        else 0.0
    )
    roas_not_computable = projected_spend <= 1e-9
    avg_roas = 0.0 if roas_not_computable else expected_revenue / projected_spend
    lower_roas = 0.0 if roas_not_computable else lower_revenue / projected_spend
    upper_roas = 0.0 if roas_not_computable else max(avg_roas, upper_revenue / projected_spend)
    model_type = (model_bundle or {}).get("model_type") or _model_type()

    return {
        "revenue": revenue,
        "roas": roas,
        "summary": ForecastSummary(
            expectedRevenue=round_money(expected_revenue),
            lowerRevenue=round_money(lower_revenue),
            upperRevenue=round_money(upper_revenue),
            avgRoas=round_money(avg_roas),
            lowerRoas=round_money(lower_roas),
            upperRoas=round_money(upper_roas),
            roasStatus="not_computable" if roas_not_computable else "computable",
            horizonDays=horizon,
            level=level,
            value=value,
            modelType=model_type,
            diagnostics=forecast_diagnostics(daily, revenue_model, roas_model, future_revenue, future_roas),
        ),
    }


def simulate_budgets(frame: pd.DataFrame, horizon: int, budgets: Dict[str, float]) -> Dict[str, Any]:
    """Project channel-level revenue after changing total budget by channel."""
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
        spend_uncertainty_pct = _spend_uncertainty_pct(
            recent["spend"],
            baseline_total_spend,
            new_total_spend,
        )
        future = _apply_spend_uncertainty(future, spend_uncertainty_pct)
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
    blended_roas = projected_roas
    roas_decomposition = []
    for item in results:
        marginal_revenue = _estimate_marginal_revenue(frame, item.channel, horizon, item.newTotalSpend)
        marginal_roas = marginal_revenue / 1000 if item.newTotalSpend > 0 else 0.0
        efficiency = 50
        if blended_roas > 0:
            efficiency += min(35, max(-35, (item.projectedRoas - blended_roas) / blended_roas * 50))
        efficiency += min(15, max(-15, (marginal_roas - 1.5) * 6))
        roas_decomposition.append(
            {
                "channel": item.channel,
                "spend": item.newTotalSpend,
                "revenue": item.projectedRevenue,
                "roas": item.projectedRoas,
                "roas_vs_blend": round_money(item.projectedRoas - blended_roas),
                "marginal_roas_estimate": round_money(marginal_roas),
                "efficiency_score": int(max(0, min(100, round(efficiency)))),
            }
        )

    return {
        "channels": results,
        "roas_decomposition": roas_decomposition,
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


def _spend_uncertainty_pct(recent_spend: pd.Series, baseline_total_spend: float, new_total_spend: float) -> float:
    """Estimate simulator uncertainty caused by spend volatility and budget shifts."""
    spend = pd.to_numeric(recent_spend, errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
    if spend.empty:
        volatility = 0.0
    else:
        mean_spend = max(float(spend.mean()), 1.0)
        volatility = float(spend.std(ddof=1) if len(spend) > 1 else 0.0) / mean_spend
    shift_pct = abs(float(new_total_spend) - float(baseline_total_spend)) / max(float(baseline_total_spend), 1.0)
    return min(0.35, max(0.0, volatility * 0.18 + shift_pct * 0.10))


def _apply_spend_uncertainty(points: List[ForecastPoint], uncertainty_pct: float) -> List[ForecastPoint]:
    if uncertainty_pct <= 1e-9:
        return points
    adjusted: List[ForecastPoint] = []
    for point in points:
        margin = max(0.0, float(point.value) * uncertainty_pct)
        adjusted.append(
            point.model_copy(
                update={
                    "lower": round_money(max(0.0, float(point.lower) - margin)),
                    "upper": round_money(float(point.upper) + margin),
                }
            )
        )
    return adjusted


def _estimate_marginal_revenue(frame: pd.DataFrame, channel: str, horizon: int, current_total_spend: float) -> float:
    channel_frame = frame[frame["channel"] == channel].copy()
    daily = aggregate_daily(channel_frame)
    if daily.empty or horizon <= 0:
        return 0.0
    current_daily = current_total_spend / horizon
    next_daily = (current_total_spend + 1000) / horizon
    current_points = [p for p in _forecast_target(daily, horizon, "revenue", forced_daily_spend=current_daily) if not p.historical]
    next_points = [p for p in _forecast_target(daily, horizon, "revenue", forced_daily_spend=next_daily) if not p.historical]
    return max(0.0, sum(p.value for p in next_points) - sum(p.value for p in current_points))


def compute_spend_response_curve(frame: pd.DataFrame, channel: str, horizon: int, current_budget: float) -> Dict[str, Any]:
    """Estimate diminishing returns for a channel at common spend multipliers."""
    channel_frame = frame[frame["channel"] == channel].copy()
    daily = aggregate_daily(channel_frame)
    if daily.empty:
        return {"curve": [], "saturation_spend": 0.0, "marginal_roas": 0.0}

    curve = []
    previous = None
    saturation_spend = 0.0
    multipliers = [0.5, 0.75, 1.0, 1.25, 1.5, 2.0]
    for multiplier in multipliers:
        spend = max(0.0, float(current_budget) * multiplier)
        daily_spend = spend / horizon if horizon else 0.0
        future = [p for p in _forecast_target(daily, horizon, "revenue", forced_daily_spend=daily_spend) if not p.historical]
        revenue = sum(p.value for p in future)
        roas = revenue / spend if spend > 0 else 0.0
        if previous is not None:
            delta_spend = spend - previous["spend"]
            delta_revenue = revenue - previous["revenue"]
            marginal = delta_revenue / delta_spend if delta_spend > 0 else 0.0
            if saturation_spend == 0.0 and marginal < 1.5:
                saturation_spend = spend
        curve.append({"spend": round_money(spend), "revenue": round_money(revenue), "roas": round_money(roas)})
        previous = {"spend": spend, "revenue": revenue}

    marginal_roas = _estimate_marginal_revenue(frame, channel, horizon, float(current_budget)) / 1000 if current_budget else 0.0
    return {
        "curve": curve,
        "saturation_spend": round_money(saturation_spend or curve[-1]["spend"]),
        "marginal_roas": round_money(marginal_roas),
    }
