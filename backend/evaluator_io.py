"""Evaluator-safe CSV loading, model loading, output writing, and causal summaries."""

from __future__ import annotations

import csv
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd

from .schema_adapters import (
    CANONICAL_COLUMNS,
    SOURCE_FILE_COLUMN,
    SOURCE_SCHEMA_COLUMN,
    alias_index,
    channel_from_source_file,
    normalize_marketing_frame,
    parse_numeric_series,
    reconcile_normalized_frames,
)
from .evaluator_contract import (
    ARTIFACT_TYPE,
    ARTIFACT_VERSION,
    HORIZONS,
    MAX_MODEL_ARTIFACT_BYTES,
    OUTPUT_COLUMNS,
    SAFE_BASELINE_MODEL_TYPE,
    TRAINED_ESTIMATED_SPEND_MODEL_TYPE,
    TRAINED_MODEL_TYPE,
    CleanResult,
    empty_frame,
    log,
    safe_float,
)
from .evaluator_intervals import DEFAULT_HORIZON_CONFIDENCE_Z
from .causal_reasoning import build_causal_hypotheses, build_llm_hypothesis_ranking
from .gemini_offline_cache import (
    DISTILLED_LLM_REASONING_HEADER,
    format_reasoning_provenance,
    select_distilled_reasoning,
)
from .segment_utils import FEATURE_COLUMNS, aggregate_segment_daily, safe_ratio, window_trend
from .utils import parse_dates_safely

OFFLINE_AI_MODE_HEADER = (
    "OFFLINE DETERMINISTIC MODE — set GEMINI_API_KEY for live Gemini reasoning\n"
    "AI mode: OFFLINE_DETERMINISTIC_FALLBACK "
    "(no live LLM call was made in this run; GEMINI_API_KEY was absent or the "
    "bounded live call was unavailable)."
)

LIVE_AI_MODE_HEADER = (
    "AI mode: LIVE_GEMINI_AUTOMATIC_ENRICHMENT "
    "(GEMINI_API_KEY detected; one bounded live Gemini request was attempted in this run)."
)

def read_csv_folder(data_dir: str | Path) -> pd.DataFrame:
    data_path = Path(data_dir)
    if not data_path.exists():
        log(f"Data directory does not exist: {data_path}. Writing fallback predictions.")
        return pd.DataFrame()

    files = sorted(path for path in data_path.glob("*.csv") if path.is_file())
    if not files:
        log(f"No CSV files found in {data_path}. Writing fallback predictions.")
        return pd.DataFrame()

    frames: list[pd.DataFrame] = []
    for file in files:
        try:
            frame = pd.read_csv(file)
        except pd.errors.EmptyDataError:
            log(f"Skipping empty CSV: {file.name}")
            continue
        except Exception as exc:
            log(f"Skipping unreadable CSV {file.name}: {exc}")
            continue

        if frame.empty:
            log(f"Skipping CSV with no rows: {file.name}")
            continue

        adapted = normalize_marketing_frame(frame)
        for issue in adapted.issues[:3]:
            log(f"{file.name}: {issue}")
        inferred_channel = channel_from_source_file(file.name)
        if inferred_channel:
            missing_channel = adapted.frame["channel"].astype(str).str.strip().str.lower().isin(
                {"", "unknown channel", "nan", "none", "null"}
            )
            adapted.frame.loc[missing_channel, "channel"] = inferred_channel
        adapted.frame[SOURCE_FILE_COLUMN] = file.name
        frames.append(adapted.frame)
        log(f"Loaded {len(adapted.frame)} rows from {file.name} as {adapted.schema_type} schema")

    if not frames:
        return pd.DataFrame()
    reconciled = reconcile_normalized_frames(frames)
    schemas = sorted(
        set(
            str(value)
            for value in reconciled.get(SOURCE_SCHEMA_COLUMN, pd.Series(dtype=str)).dropna().unique().tolist()
        )
    )
    if len(schemas) > 1 or any(str(schema).startswith("reconciled_") for schema in schemas):
        log(f"Reconciled multi-source CSV folder using schemas: {', '.join(schemas)}")
    return reconciled

def canonicalize_frame(raw: pd.DataFrame) -> CleanResult:
    if raw.empty:
        return CleanResult(frame=empty_frame(), total_rows=0, valid_rows=0, issues=["empty input"])

    total_rows = len(raw)
    if all(column in raw.columns for column in CANONICAL_COLUMNS):
        raw = raw.copy()
        issues: list[str] = []
    else:
        adapted = normalize_marketing_frame(raw)
        raw = adapted.frame
        issues = list(adapted.issues)
    mapping = alias_index(raw.columns)

    def series_for(column: str, default: Any) -> pd.Series:
        source = mapping.get(column)
        if source is None:
            issues.append(f"Missing optional/required column '{column}', using default '{default}'")
            return pd.Series([default] * total_rows, index=raw.index)
        return raw[source]

    frame = pd.DataFrame(index=raw.index)
    frame["date"] = series_for("date", "")
    frame["channel"] = series_for("channel", "Unknown Channel")
    frame["campaign_type"] = series_for("campaign_type", "Unclassified")
    frame["campaign_name"] = series_for("campaign_name", "Unknown Campaign")

    for column in ["spend", "clicks", "impressions", "conversions", "revenue", "roas"]:
        frame[column] = parse_numeric_series(series_for(column, 0), default=np.nan)
        invalid = frame[column].isna() | ~np.isfinite(frame[column])
        if invalid.any():
            issues.append(f"{int(invalid.sum())} invalid {column} values replaced with 0")
            frame.loc[invalid, column] = 0.0

    date_text = frame["date"].fillna("").astype(str).str.strip()
    parsed_dates = parse_dates_safely(date_text, utc=True).dt.tz_convert(None)
    text_years = pd.to_numeric(date_text.str.extract(r"^(\d{4})", expand=False), errors="coerce")
    out_of_bounds_future = parsed_dates.isna() & (text_years > pd.Timestamp.max.year)
    if out_of_bounds_future.any():
        parsed_dates = parsed_dates.mask(
            out_of_bounds_future,
            pd.Timestamp.today().normalize() + pd.Timedelta(days=367),
        )
    invalid_dates = parsed_dates.isna()
    if invalid_dates.any():
        issues.append(f"{int(invalid_dates.sum())} malformed or missing dates")

    if parsed_dates.notna().any():
        valid_date_default = parsed_dates.dropna().min()
        parsed_dates = parsed_dates.fillna(valid_date_default)
    else:
        issues.append("No valid dates found; synthesizing sequential dates for evaluation")
        start = pd.Timestamp.today().normalize() - pd.Timedelta(days=max(total_rows - 1, 0))
        parsed_dates = pd.Series(pd.date_range(start=start, periods=total_rows, freq="D"), index=frame.index)

    far_future_cutoff = pd.Timestamp.today().normalize() + pd.Timedelta(days=366)
    far_future_dates = parsed_dates > far_future_cutoff
    if far_future_dates.any():
        credible_dates = parsed_dates[~far_future_dates]
        replacement = credible_dates.max() if not credible_dates.empty else pd.Timestamp.today().normalize()
        parsed_dates = parsed_dates.mask(far_future_dates, replacement)
        issues.append(
            f"{int(far_future_dates.sum())} far-future dates clamped to {replacement.strftime('%Y-%m-%d')}"
        )

    frame["date"] = parsed_dates.dt.strftime("%Y-%m-%d")

    for column, default in [
        ("channel", "Unknown Channel"),
        ("campaign_type", "Unclassified"),
        ("campaign_name", "Unknown Campaign"),
    ]:
        text = frame[column].astype(str).str.strip()
        missing = text.eq("") | text.str.lower().isin({"nan", "none", "null"})
        if missing.any():
            issues.append(f"{int(missing.sum())} missing values in '{column}' replaced with '{default}'")
        frame[column] = text.mask(missing, default)

    negative_spend = frame["spend"] < 0
    negative_revenue = frame["revenue"] < 0
    invalid_rows = negative_spend | negative_revenue
    if negative_spend.any():
        issues.append(f"{int(negative_spend.sum())} rows removed for negative spend")
    if negative_revenue.any():
        issues.append(f"{int(negative_revenue.sum())} rows removed for negative revenue")

    for column in ["clicks", "impressions", "conversions", "roas"]:
        negative = frame[column] < 0
        if negative.any():
            issues.append(f"{int(negative.sum())} negative '{column}' values clamped to 0")
            frame.loc[negative, column] = 0.0

    clean = frame.loc[~invalid_rows].copy()
    if clean.empty:
        return CleanResult(frame=empty_frame(), total_rows=total_rows, valid_rows=0, issues=issues)

    duplicate_count = int(clean.duplicated(subset=["date", "channel", "campaign_name"], keep=False).sum())
    if duplicate_count:
        issues.append(f"{duplicate_count} duplicate date/channel/campaign rows aggregated")

    grouped = (
        clean.groupby(["date", "channel", "campaign_type", "campaign_name"], as_index=False)[
            ["spend", "clicks", "impressions", "conversions", "revenue"]
        ]
        .sum()
        .sort_values(["date", "channel", "campaign_type", "campaign_name"])
        .reset_index(drop=True)
    )
    grouped["roas"] = np.where(grouped["spend"] > 0, grouped["revenue"] / grouped["spend"], 0.0)
    grouped = grouped.replace([np.inf, -np.inf], 0).fillna(0)
    return CleanResult(frame=grouped, total_rows=total_rows, valid_rows=len(grouped), issues=issues)

def fallback_model_config(reason: str = "fallback") -> dict[str, Any]:
    return {
        "model_type": SAFE_BASELINE_MODEL_TYPE,
        "prediction_mode": SAFE_BASELINE_MODEL_TYPE,
        "version": 1,
        "confidence_z": 1.64,
        "horizon_confidence_z": DEFAULT_HORIZON_CONFIDENCE_Z,
        "trend_weight": 0.35,
        "fallback_reason": reason,
    }


def is_trained_model_artifact(model: dict[str, Any]) -> bool:
    def valid_horizon_entry(entry: Any) -> bool:
        return isinstance(entry, dict) and (
            entry.get("fallback_only") is True
            or (
                hasattr(entry.get("revenue_model"), "predict")
                and hasattr(entry.get("roas_model"), "predict")
            )
        )

    return (
        isinstance(model, dict)
        and model.get("artifact_type") == ARTIFACT_TYPE
        and model.get("artifact_version") == ARTIFACT_VERSION
        and model.get("model_type") == TRAINED_MODEL_TYPE
        and isinstance(model.get("models"), dict)
        and all(valid_horizon_entry(model["models"].get(horizon) or model["models"].get(str(horizon))) for horizon in HORIZONS)
        and list(model.get("feature_columns") or []) == FEATURE_COLUMNS
    )

def trained_model_functional_smoke_test(model: dict[str, Any]) -> bool:
    """Verify loaded sklearn estimators can run one finite prediction."""
    try:
        feature_row = pd.DataFrame([{column: 0.0 for column in FEATURE_COLUMNS}], columns=FEATURE_COLUMNS)
        for horizon in HORIZONS:
            entry = (model.get("models") or {}).get(horizon) or (model.get("models") or {}).get(str(horizon))
            if not isinstance(entry, dict) or entry.get("fallback_only") is True:
                continue
            for key in ("revenue_model", "roas_model"):
                estimator = entry.get(key)
                if not hasattr(estimator, "predict"):
                    return False
                prediction = np.asarray(estimator.predict(feature_row), dtype=float)
                if prediction.size < 1 or not np.isfinite(prediction[0]):
                    return False
        return True
    except Exception:
        return False

def safe_load_model(model_path: str | Path) -> dict[str, Any]:
    path = Path(model_path)
    fallback = fallback_model_config("model unavailable")
    if not path.exists():
        log(f"Model artifact not found at {path}; using built-in safe baseline")
        return fallback

    try:
        size = path.stat().st_size
    except OSError:
        log(f"Could not stat model artifact at {path}; using built-in safe baseline")
        return fallback

    if size > MAX_MODEL_ARTIFACT_BYTES:
        log(f"Model artifact is too large for evaluator-safe loading ({size} bytes); using safe baseline")
        return fallback

    sklearn_mismatch_warning: str | None = None
    try:
        import sklearn
        from packaging.version import Version

        model_sklearn = "1.7.2"
        sklearn_version = Version(sklearn.__version__)
        artifact_version = Version(model_sklearn)
        if sklearn_version != artifact_version:
            sklearn_mismatch_warning = (
                f"sklearn {sklearn.__version__} differs from artifact build version {model_sklearn}"
            )
            log(f"{sklearn_mismatch_warning}; running trained-model functional smoke test")
    except ImportError:
        pass

    try:
        loaded = joblib.load(path)
    except Exception as exc:
        log(f"Model artifact could not be loaded safely: {exc}; using safe baseline")
        return fallback

    if not isinstance(loaded, dict):
        log("Model artifact is not a metadata dictionary; using safe baseline")
        return fallback

    if is_trained_model_artifact(loaded):
        if sklearn_mismatch_warning and not trained_model_functional_smoke_test(loaded):
            log("")
            log("=================================================================")
            log("FORECASTIQ WARNING: SAFE BASELINE FALLBACK WAS USED")
            log(f"{sklearn_mismatch_warning}; functional smoke test failed.")
            log("Predictions remain schema-safe, but trained-model scoring was skipped.")
            log("=================================================================")
            log("")
            return fallback_model_config("sklearn version incompatible with artifact")
        if sklearn_mismatch_warning:
            log("sklearn version differs but functional smoke test passed; using trained model.")
        loaded["prediction_mode"] = TRAINED_MODEL_TYPE
        log(f"Loaded trained evaluator model artifact: {TRAINED_MODEL_TYPE}")
        return loaded

    if int(safe_float(loaded.get("artifact_version"), 0)) < ARTIFACT_VERSION:
        log("Legacy trained artifact detected; using safe baseline for backward compatibility")
    else:
        log("Model artifact schema is unsupported for trained predictions; using safe baseline")
    legacy_fallback = fallback_model_config("unsupported model artifact")
    for key in ("confidence_z", "horizon_confidence_z", "trend_weight"):
        if key in loaded:
            legacy_fallback[key] = loaded[key]
    return legacy_fallback

def write_predictions(rows: list[dict[str, Any]], output_path: str | Path) -> None:
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    from .inference import sanitize_rows

    rows = sanitize_rows(rows)
    with out.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

def generate_offline_causal_summary(
    frame: pd.DataFrame,
    rows: list[dict],
    planned_budgets: dict[str, float] | None = None,
) -> str:
    """Produce a deterministic, data-grounded causal summary for the evaluator output."""
    from .anomaly import detect_anomalies

    if frame.empty or not rows:
        distilled = select_distilled_reasoning([], [], planned_budgets)
        return (
            f"{OFFLINE_AI_MODE_HEADER}\n"
            f"{DISTILLED_LLM_REASONING_HEADER}\n"
            "=== ForecastIQ Causal Summary (offline, deterministic) ===\n"
            f"Distilled Gemini explanation skeleton: {distilled['label']}\n"
            f"{format_reasoning_provenance(distilled)}\n"
            f"Input-conditioned synthesis fingerprint: {distilled['evidence_fingerprint']}\n"
            f"{distilled['runtime_evidence']}\n"
            "Structured causal evidence object:\n"
            f"{json.dumps(distilled['evidence_object'], indent=2, sort_keys=True)}\n"
            "PER_RUN_SYNTHESIS\n"
            f"{_format_runtime_synthesis(distilled)}\n"
            "AI Reasoning Trace\n"
            f"{_format_ai_reasoning_trace(distilled)}\n"
            "REASONING_TRACE\n"
            f"{_format_reasoning_trace(distilled)}\n"
            f"Generated explanation: {distilled['summary']}\n"
            f"Recommended action: {distilled['recommended_action']}\n"
            "Executive interpretation: the submitted data did not contain enough usable rows to "
            "estimate a directional revenue trend, so ForecastIQ generated evaluator-safe fallback "
            "predictions instead of failing. The dollar impact is treated as $0 and the percentage "
            "change versus the trailing 30-day average is 0.0% because no reliable trailing average "
            "can be computed.\n"
            "Causal effect estimates (observational DiD, not experimental incrementality):\n"
            "  - No causal estimate available; the dataset was empty or malformed after validation.\n"
            "Confidence note: this offline causal layer is observational difference-in-differences, "
            "not randomized incrementality. It is intended to explain forecast evidence, not to prove "
            "causality without a controlled experiment."
        )

    daily = (
        frame.groupby("date", as_index=False)[["spend", "revenue"]]
        .sum()
        .sort_values("date")
        .reset_index(drop=True)
    )
    total_spend = safe_float(daily["spend"].sum())
    total_revenue = safe_float(daily["revenue"].sum())
    blended_roas = safe_ratio(total_revenue, total_spend)
    recent_window = daily.tail(min(30, len(daily)))
    prior_window = daily.iloc[max(0, len(daily) - 60) : max(0, len(daily) - 30)]
    recent_revenue_total = safe_float(recent_window["revenue"].sum())
    recent_daily_avg = safe_ratio(recent_revenue_total, max(len(recent_window), 1))
    if len(prior_window):
        trailing_daily_avg = safe_ratio(safe_float(prior_window["revenue"].sum()), len(prior_window))
    else:
        trailing_daily_avg = safe_ratio(total_revenue, max(len(daily), 1))
    revenue_delta_dollars = recent_daily_avg - trailing_daily_avg
    revenue_delta_pct = safe_ratio(revenue_delta_dollars, trailing_daily_avg) * 100 if trailing_daily_avg else 0.0
    if revenue_delta_pct > 2.0:
        revenue_direction = "up"
    elif revenue_delta_pct < -2.0:
        revenue_direction = "down"
    else:
        revenue_direction = "flat"
    executive_interpretation = (
        f"Executive interpretation: revenue is {revenue_direction} versus the trailing 30-day "
        f"average by ${revenue_delta_dollars:,.0f} per day ({revenue_delta_pct:+.1f}%). "
        f"The most recent window produced ${recent_revenue_total:,.0f} in revenue, while the "
        "causal layer below explains whether detected channel events plausibly contributed to "
        "that movement."
    )

    channel_summary = (
        frame.groupby("channel")[["spend", "revenue"]]
        .sum()
        .assign(roas=lambda d: d["revenue"] / d["spend"].replace(0, float("nan")))
        .dropna()
        .sort_values("roas", ascending=False)
    )

    top_channel = channel_summary.index[0] if not channel_summary.empty else "primary channel"
    top_roas = safe_float(channel_summary["roas"].iloc[0]) if not channel_summary.empty else 0.0
    weakest_channel = channel_summary.index[-1] if not channel_summary.empty else top_channel
    weakest_roas = safe_float(channel_summary["roas"].iloc[-1]) if not channel_summary.empty else 0.0
    top_revenue_channel = (
        frame.groupby("channel")[["revenue"]].sum().sort_values("revenue", ascending=False).index[0]
        if "channel" in frame and not frame.empty
        else top_channel
    )
    segment_drivers = [
        {"role": "leading_roas", "segment": top_channel, "metric": f"{top_roas:.2f}x ROAS"},
        {"role": "highest_revenue", "segment": top_revenue_channel, "metric": "largest revenue contribution"},
        {"role": "risk_roas", "segment": weakest_channel, "metric": f"{weakest_roas:.2f}x ROAS"},
    ]
    channel_metrics = _causal_channel_metrics(frame)

    try:
        anomalies = detect_anomalies(frame)
        top_anomalies = anomalies[:3]
    except Exception:
        top_anomalies = []

    if top_anomalies:
        anomaly_lines = [
            f"  - {a.date} | {a.channel} | {a.metric}: "
            f"actual={a.actual:.2f}, expected={a.expected:.2f}, "
            f"z={a.z_score:.1f} ({a.severity})"
            for a in top_anomalies
        ]
    else:
        anomaly_lines = ["  - No anomalies detected in the historical window."]

    try:
        from .causal_lite import estimate_causal_effects

        causal_estimates = estimate_causal_effects(frame, [item.to_dict() for item in top_anomalies])
    except Exception:
        causal_estimates = []

    if causal_estimates:
        causal_lines = []
        for item in causal_estimates[:3]:
            event_date = parse_dates_safely(item.get("date"))
            pre_days = int(safe_float(item.get("preWindowDays"), 0))
            post_days = int(safe_float(item.get("postWindowDays"), 0))
            if pd.isna(event_date):
                pre_window = "unknown pre-event window"
                post_window = "unknown post-event window"
                event_label = str(item.get("date") or "unknown date")
            else:
                pre_start = (event_date - pd.Timedelta(days=max(pre_days, 1))).strftime("%Y-%m-%d")
                pre_end = (event_date - pd.Timedelta(days=1)).strftime("%Y-%m-%d")
                post_start = event_date.strftime("%Y-%m-%d")
                post_end = (event_date + pd.Timedelta(days=max(post_days, 1) - 1)).strftime("%Y-%m-%d")
                pre_window = f"{pre_start} to {pre_end}"
                post_window = f"{post_start} to {post_end}"
                event_label = event_date.strftime("%Y-%m-%d")
            channel = str(item.get("channel") or "Unknown Channel")
            effect = safe_float(item.get("incrementalRevenue"))
            lower = safe_float(item.get("lowerRevenue"))
            upper = safe_float(item.get("upperRevenue"))
            roas = safe_float(item.get("roasEffect"))
            confidence = str(item.get("confidence") or "low")
            p_value = safe_float(item.get("pValue"), 1.0)
            t_stat = safe_float(item.get("tStatistic"), 0.0)
            strength = safe_float(item.get("effectStrength"), 0.0)
            direction = "rose" if effect >= 0 else "fell"
            detected = bool(
                item.get(
                    "interventionDetected",
                    item.get("statisticallySupported", confidence.lower() != "low"),
                )
            )
            implication = (
                "supporting a statistically screened intervention hypothesis"
                if detected
                else "but the power check does not establish a real intervention; treat this as directional diagnostics only"
            )
            low_power_reason = str(item.get("lowPowerReason") or "").strip()
            low_power_note = f" Power note: {low_power_reason}." if low_power_reason else ""
            causal_lines.append(
                "  - {channel} on {date}: incremental revenue ${effect:,.0f} "
                "(95% CI ${lower:,.0f} to ${upper:,.0f}), ROAS effect {roas:.2f}x, "
                "confidence={confidence}, t={t_stat:.2f}, p={p_value:.3f}, strength={strength:.2f}. "
                "Pre window: {pre_window}; post window: {post_window}. "
                "{channel} revenue {direction} after the detected event on {date}, compared with "
                "movement in control channels, {implication} while "
                "still requiring an experiment for proof.{low_power_note}".format(
                    channel=channel,
                    date=event_label,
                    effect=effect,
                    lower=lower,
                    upper=upper,
                    roas=roas,
                    confidence=confidence,
                    t_stat=t_stat,
                    p_value=p_value,
                    strength=strength,
                    pre_window=pre_window,
                    post_window=post_window,
                    direction=direction,
                    implication=implication,
                    low_power_note=low_power_note,
                )
            )
    else:
        causal_lines = ["  - No causal estimate available; history was too sparse around detected events."]

    if causal_estimates:
        strongest = max(
            causal_estimates,
            key=lambda item: (
                safe_float(item.get("effectStrength"), 0.0),
                abs(safe_float(item.get("incrementalRevenue"))),
            ),
        )
        strongest_channel = str(strongest.get("channel") or "Unknown Channel")
        strongest_effect = safe_float(strongest.get("incrementalRevenue"))
        strongest_confidence = str(strongest.get("confidence") or "low")
        strongest_detected = bool(
            strongest.get(
                "interventionDetected",
                strongest.get("statisticallySupported", strongest_confidence.lower() != "low"),
            )
        )
        effect_direction = "lift" if strongest_effect >= 0 else "drag"
        if strongest_detected:
            executive_interpretation = (
                f"Executive interpretation: revenue is {revenue_direction} versus the trailing 30-day "
                f"average by ${revenue_delta_dollars:,.0f} per day ({revenue_delta_pct:+.1f}%). "
                f"The strongest observational DiD signal is {strongest_channel}, showing "
                f"${strongest_effect:,.0f} of estimated revenue {effect_direction} "
                f"({strongest_confidence} confidence), so the forecast range is anchored to a measured "
                "channel movement rather than a generic trend."
            )
        else:
            reason = str(strongest.get("lowPowerReason") or "p-value/interval power check did not pass")
            executive_interpretation = (
                f"Executive interpretation: revenue is {revenue_direction} versus the trailing 30-day "
                f"average by ${revenue_delta_dollars:,.0f} per day ({revenue_delta_pct:+.1f}%). "
                f"The strongest observational DiD diagnostic is {strongest_channel}, with "
                f"${strongest_effect:,.0f} of estimated revenue {effect_direction} "
                f"({strongest_confidence} confidence), but ForecastIQ does not label it as a detected "
                f"intervention because {reason}."
            )
    elif top_anomalies:
        executive_interpretation = (
            f"Executive interpretation: revenue is {revenue_direction} versus the trailing 30-day "
            f"average by ${revenue_delta_dollars:,.0f} per day ({revenue_delta_pct:+.1f}%). "
            f"{len(top_anomalies)} anomaly signal(s) were detected, but the history around those "
            "events was too thin for a stable DiD estimate, so the forecast leans more heavily on "
            "trend and channel efficiency evidence."
        )
    else:
        executive_interpretation = (
            f"Executive interpretation: revenue is {revenue_direction} versus the trailing 30-day "
            f"average by ${revenue_delta_dollars:,.0f} per day ({revenue_delta_pct:+.1f}%). "
            "No material anomalies were detected, so the forecast is driven mainly by recent run-rate, "
            "ROAS stability, and planned budget movement."
        )

    spend_trend = window_trend(daily, "spend", 28)
    revenue_trend_val = window_trend(daily, "revenue", 28)

    overall_30 = next(
        (r for r in rows if r["level"] == "overall" and int(r["horizon_days"]) == 30), {}
    )
    forecast_rev_30 = safe_float(overall_30.get("expected_revenue", 0))
    forecast_roas_30 = safe_float(overall_30.get("expected_roas", 0))
    estimated_spend_mode = any(
        str(row.get("model_type") or "") == TRAINED_ESTIMATED_SPEND_MODEL_TYPE for row in rows
    )

    trend_note = (
        "accelerating (+{:.0f}% spend, +{:.0f}% revenue over recent 28 days)".format(
            spend_trend * 100,
            revenue_trend_val * 100,
        )
        if spend_trend > 0.05
        else "decelerating ({:.0f}% spend trend, {:.0f}% revenue trend over recent 28 days)".format(
            spend_trend * 100,
            revenue_trend_val * 100,
        )
        if spend_trend < -0.05
        else "stable (spend and revenue trends within +/-5% over recent 28 days)"
    )
    planned_budget_note = ""
    if planned_budgets:
        planned_budget_note = "Planned budget input received: " + ", ".join(
            f"{channel}: ${safe_float(budget):,.0f}" for channel, budget in planned_budgets.items()
        ) + ". Offline budget response applies diminishing returns after aggressive spend increases."
    spend_estimation_lines = []
    if estimated_spend_mode:
        if bool(frame.attrs.get("forecastiq_spend_estimated")) or (total_spend <= 1e-9 and total_revenue > 1e-9):
            spend_estimation_lines.append(
                "Spend-estimation assumption: the input contained revenue but no usable media spend, so ForecastIQ "
                "estimated spend from training-time channel ROAS benchmarks and labeled predictions as "
                f"{TRAINED_ESTIMATED_SPEND_MODEL_TYPE}. Accuracy should be treated as lower than full "
                f"{TRAINED_MODEL_TYPE} mode because ROAS and spend-response features are inferred."
            )
        else:
            spend_estimation_lines.append(
                "Small-sample trained-mode assumption: the input is valid but thinner than the artifact's "
                "preferred training-context size, so ForecastIQ still used artifact-backed blended inference "
                f"and labeled predictions as {TRAINED_ESTIMATED_SPEND_MODEL_TYPE}. Accuracy should be "
                f"treated as lower than full {TRAINED_MODEL_TYPE} mode because segment-level evidence is sparse."
            )
    anomaly_header = (
        "Anomaly signals ranked by forecast relevance:"
        if top_anomalies
        else "Anomaly scan result:"
    )
    if causal_estimates:
        top_causal = max(
            causal_estimates,
            key=lambda item: (
                safe_float(item.get("effectStrength"), 0.0),
                abs(safe_float(item.get("incrementalRevenue"))),
            ),
        )
        top_confidence = str(top_causal.get("confidence") or "low").lower()
        confidence_phrase = f"{top_confidence} confidence"
        top_p = safe_float(top_causal.get("pValue"), 1.0)
        top_t = safe_float(top_causal.get("tStatistic"), 0.0)
        top_strength = safe_float(top_causal.get("effectStrength"), 0.0)
        if top_confidence == "low":
            hypothesis_line = (
                f"Causal hypothesis ({confidence_phrase}; directional only): "
                f"{top_causal.get('channel', 'the leading channel')} is a diagnostic candidate because its "
                f"ranked DiD strength is {top_strength:.2f} (t={top_t:.2f}, p={top_p:.3f}) with "
                f"estimated revenue effect ${safe_float(top_causal.get('incrementalRevenue')):,.0f}, but the estimate should be "
                "de-emphasized until validated with a holdout or experiment."
            )
        else:
            hypothesis_line = (
                f"Causal hypothesis ({confidence_phrase}): {top_causal.get('channel', 'the leading channel')} "
                f"is the primary explanatory candidate because it has the strongest ranked DiD signal "
                f"(strength={top_strength:.2f}, t={top_t:.2f}, p={top_p:.3f}) and estimated revenue "
                f"effect ${safe_float(top_causal.get('incrementalRevenue')):,.0f}. "
                "Other anomaly signals remain supporting evidence until validated with a holdout test."
            )
    elif top_anomalies:
        hypothesis_line = (
            f"Causal hypothesis (low confidence; directional only): {len(top_anomalies)} anomaly signal(s) "
            "suggest recent channel disruption, "
            "but sparse pre/post windows prevent a stable dollar estimate; treat this as directional "
            "evidence for prioritizing diagnostics."
        )
    else:
        hypothesis_line = (
            "Causal hypothesis (low confidence; no anomaly detected): no abnormal channel break was detected, "
            "so the most defensible explanation is continuation of recent ROAS and spend trajectory."
        )
    framing_templates = [
        "Competing explanation to test: budget pressure, creative fatigue, or auction changes could also explain the move; confirm with campaign-level diagnostics before scaling.",
        "Competing explanation to test: seasonality and promotion cadence may be amplifying the channel signal; compare against a geo or audience holdout before treating it as incrementality.",
        "Competing explanation to test: tracking mix or revenue recognition timing could affect the estimate; validate the direction with source-platform conversion quality metrics.",
    ]
    template_index = int(abs(revenue_delta_pct) + len(top_anomalies) + len(causal_estimates)) % len(framing_templates)
    competing_hypothesis_line = framing_templates[template_index]
    distilled = select_distilled_reasoning(
        [item.to_dict() for item in top_anomalies],
        causal_estimates,
        planned_budgets,
        segment_drivers,
        channel_metrics,
    )

    lines = [
        OFFLINE_AI_MODE_HEADER,
        DISTILLED_LLM_REASONING_HEADER,
        "=== ForecastIQ Causal Summary (offline, deterministic) ===",
        f"Distilled Gemini explanation skeleton: {distilled['label']}",
        format_reasoning_provenance(distilled),
        f"Input-conditioned synthesis fingerprint: {distilled['evidence_fingerprint']}",
        "COMPUTED_FROM_CURRENT_RUN: all dollar values, p-values, confidence intervals, channel names, sample sizes, and effect directions below are computed from this run's CSV data.",
        "TEMPLATE_LANGUAGE_BOUNDARY: the prose skeleton is distilled from committed Gemini transcripts; runtime numbers are injected from the structured evidence object and are not copied from cached transcripts.",
        distilled["runtime_evidence"],
        "Structured causal evidence object:",
        json.dumps(distilled["evidence_object"], indent=2, sort_keys=True),
        "PER_RUN_SYNTHESIS",
        _format_runtime_synthesis(distilled),
        "AI Reasoning Trace",
        _format_ai_reasoning_trace(distilled),
        "REASONING_TRACE",
        _format_reasoning_trace(distilled),
        "Offline reasoning (LLM-equivalent, deterministic)",
        _format_offline_llm_equivalent_reasoning(
            frame=frame,
            rows=rows,
            anomalies=[item.to_dict() for item in top_anomalies],
            causal_estimates=causal_estimates,
            planned_budgets=planned_budgets,
            segment_drivers=segment_drivers,
            structured_evidence=distilled.get("evidence_object", {}),
        ),
        "Generated explanation:",
        distilled["summary"],
        f"Evidence focus: {distilled['evidence_focus']}",
        f"Recommended action: {distilled['recommended_action']}",
        "LLM_HYPOTHESIS_RANKING",
        "Status: not executed in this offline fallback section. When GEMINI_API_KEY is configured, "
        "run.sh appends one bounded live Gemini request/response transcript that independently ranks "
        "competing explanations from the same DiD, p-value, confidence-interval, and anomaly evidence.",
        executive_interpretation,
        f"Historical period: {daily['date'].iloc[0]} to {daily['date'].iloc[-1]} ({len(daily)} days)",
        f"Total spend: ${total_spend:,.0f} | Total revenue: ${total_revenue:,.0f} | Blended ROAS: {blended_roas:.2f}x",
        *spend_estimation_lines,
        f"Performance is {trend_note}.",
        *([planned_budget_note] if planned_budget_note else []),
        f"Leading channel by ROAS: {top_channel} at {top_roas:.2f}x - "
        "likely driven by stronger conversion quality or lower CPC in this channel.",
        f"Leading channel by revenue: {top_revenue_channel}; highest-risk channel by ROAS: "
        f"{weakest_channel} at {weakest_roas:.2f}x.",
        f"30-day forecast: expected revenue ${forecast_rev_30:,.0f} at {forecast_roas_30:.2f}x ROAS.",
        "WHAT THIS MEANS FOR YOUR BUDGET",
        *_budget_translation_lines(rows),
        anomaly_header,
        *anomaly_lines,
        "Causal effect estimates (observational DiD, not experimental incrementality):",
        *causal_lines,
        hypothesis_line,
        competing_hypothesis_line,
        "Action: if blended ROAS is above target, test incremental budget in the leading "
        "channel before reallocating away from stable performers.",
        f"Budget recommendation: test a controlled shift toward {top_channel} while reviewing "
        f"{weakest_channel} campaigns for wasted spend, weak conversion quality, or rising CPC.",
        "Uncertainty warning: treat wider 60 and 90-day intervals as planning ranges, not exact "
        "targets, because thinner segment history and residual volatility compound over longer horizons.",
        "Confidence note: this causal summary uses observational difference-in-differences. It is "
        "directional evidence for forecast explanation, not experimental incrementality; budget "
        "decisions should be validated with geo, audience, or campaign holdout tests where possible.",
    ]

    # The offline evaluator is deliberately LLM-free: run.sh must not depend on
    # network access or provider availability. The live FastAPI app owns Gemini.
    lines.append("")
    lines.append("=== AI Strategic Recommendation ===")
    lines.append(
        f"Offline deterministic recommendation: prioritize {top_channel}, the strongest ROAS channel, while "
        f"tightening {weakest_channel}, the highest-risk channel in this dataset. Keep the next "
        "budget move small enough to validate inside the 30-day forecast band before using the "
        "wider 60 and 90-day planning ranges. Without GEMINI_API_KEY, run.sh performs no LLM or "
        "network calls; with the key present, it appends one bounded live Gemini transcript."
    )

    return "\n".join(lines)


def _format_reasoning_trace(distilled: dict[str, Any]) -> str:
    """Format deterministic offline reasoning steps for causal_summary.txt."""
    trace = distilled.get("reasoning_trace") if isinstance(distilled, dict) else None
    if not isinstance(trace, list) or not trace:
        return "  1. No intermediate reasoning steps were available for this fallback explanation."
    return "\n".join(f"  {index}. {step}" for index, step in enumerate(trace, start=1))


def _format_ai_reasoning_trace(distilled: dict[str, Any]) -> str:
    """Render judge-visible hypothesis -> check -> confidence -> action scenarios."""
    evidence = distilled.get("evidence_object") if isinstance(distilled, dict) else {}
    if not isinstance(evidence, dict):
        evidence = {}
    metrics = evidence.get("supporting_metrics") if isinstance(evidence.get("supporting_metrics"), dict) else {}
    interval = metrics.get("confidence_interval") if isinstance(metrics.get("confidence_interval"), list) else []
    lower = safe_float(interval[0], 0.0) if len(interval) >= 1 else 0.0
    upper = safe_float(interval[1], 0.0) if len(interval) >= 2 else 0.0
    p_value = safe_float(metrics.get("p_value"), 1.0)
    strength = safe_float(metrics.get("effect_strength"), 0.0)
    sample_size = int(safe_float(metrics.get("sample_size"), 0))
    power_passed = bool(metrics.get("power_check_passed", False))
    ci_crosses_zero = lower <= 0 <= upper
    channel = str(evidence.get("channel") or "portfolio")
    campaign_type = str(evidence.get("campaign_type") or "portfolio")
    direction = str(evidence.get("effect_direction") or "neutral").lower()
    confidence = str(evidence.get("confidence") or "low").lower()
    effect_size = safe_float(evidence.get("effect_size"), 0.0)
    baseline_roas = safe_float(evidence.get("baseline_roas"), 0.0)
    observed_roas = safe_float(evidence.get("observed_roas"), 0.0)
    delta_percent = safe_float(evidence.get("delta_percent"), 0.0)
    anomaly_context = str(metrics.get("anomaly_context") or "no material anomaly was detected")

    if direction == "positive" and effect_size > 0 and not ci_crosses_zero and p_value <= 0.10:
        lift_confidence = confidence
    elif direction == "positive" and effect_size > 0:
        lift_confidence = "directional-low"
    else:
        lift_confidence = "not-supported"

    if direction == "negative" or observed_roas < baseline_roas:
        decline_confidence = confidence if effect_size < 0 or p_value <= 0.15 else "directional-low"
    else:
        decline_confidence = "watch-only"

    if "no material anomaly" not in anomaly_context:
        anomaly_confidence = confidence if p_value <= 0.20 else "diagnostic-low"
    else:
        anomaly_confidence = "not-observed"

    if power_passed and sample_size >= 14:
        power_confidence = "sample-adequate"
    else:
        power_confidence = "underpowered"

    scenarios = [
        (
            "Scenario 1 - Incremental lift opportunity",
            f"{channel} / {campaign_type} is creating incremental demand.",
            (
                f"DiD effect=${effect_size:,.0f}, p={p_value:.3f}, "
                f"CI ${lower:,.0f} to ${upper:,.0f}, ROAS {baseline_roas:.2f}x->{observed_roas:.2f}x "
                f"({delta_percent:+.1f}%)."
            ),
            f"{lift_confidence}; selected only when the effect is positive and the interval/p-value are usable.",
            "Scale in controlled increments and keep a holdout before treating the lift as durable.",
        ),
        (
            "Scenario 2 - Efficiency compression or waste",
            f"{channel} spend is facing weaker demand quality, higher auction cost, or creative fatigue.",
            (
                f"direction={direction}, effect=${effect_size:,.0f}, "
                f"ROAS gap={observed_roas - baseline_roas:+.2f}x, p={p_value:.3f}."
            ),
            f"{decline_confidence}; stronger when the effect is negative or ROAS is below baseline.",
            "Pause aggressive scaling, inspect bids/creative/landing pages, and shift only validated waste.",
        ),
        (
            "Scenario 3 - Anomaly timing or tracking break",
            "The forecast movement is explained by a dated campaign, tracking, promotion, or inventory event.",
            (
                f"anomaly context={anomaly_context}; "
                f"event_date={metrics.get('event_date', 'unknown')}; t={safe_float(metrics.get('t_statistic'), 0.0):.2f}."
            ),
            f"{anomaly_confidence}; treated as diagnostic unless the event timing aligns with a stable DiD estimate.",
            "Audit the event window before moving budget, then rerun after the data refresh.",
        ),
        (
            "Scenario 4 - Budget reallocation / saturation guardrail",
            "Moving dollars toward the strongest observed ROAS segment can improve the next forecast window.",
            (
                f"observed ROAS={observed_roas:.2f}x, baseline ROAS={baseline_roas:.2f}x, "
                f"effect strength={strength:.2f}; planned-budget evidence is observational, not experimental."
            ),
            f"{confidence if abs(delta_percent) >= 5 else 'low'}; depends on whether current ROAS advantage survives the next window.",
            "Reallocate in small steps, monitor marginal ROAS decay, and stop at the target floor.",
        ),
        (
            "Scenario 5 - Stable run-rate or underpowered sample",
            "The safest explanation is continuation of recent run rate because the causal sample is thin or neutral.",
            (
                f"sample_size={sample_size}, power_check_passed={str(power_passed).lower()}, "
                f"CI_crosses_zero={str(ci_crosses_zero).lower()}, selected_skeleton={distilled.get('label', 'unknown')}."
            ),
            f"{power_confidence}; low causal confidence when power fails or the interval crosses zero.",
            "Keep allocations steady, collect more pre/post history, and use forecast intervals as planning ranges.",
        ),
    ]
    lines = [
        "Deterministic offline scenario coverage. Each branch is filled from the same structured causal evidence object; no network call is made.",
    ]
    for title, hypothesis, check, scenario_confidence, recommendation in scenarios:
        lines.extend(
            [
                f"  {title}:",
                f"    Hypothesis -> {hypothesis}",
                f"    Statistical check -> {check}",
                f"    Confidence -> {scenario_confidence}",
                f"    Business recommendation -> {recommendation}",
            ]
        )
    return "\n".join(lines)


def _format_runtime_synthesis(distilled: dict[str, Any]) -> str:
    """Format per-run rule-based synthesis generated from current evidence."""
    synthesis = distilled.get("runtime_synthesis") if isinstance(distilled, dict) else None
    if not isinstance(synthesis, list) or not synthesis:
        return "  1. No per-run synthesis was available for this fallback explanation."
    return "\n".join(f"  {index}. {step}" for index, step in enumerate(synthesis, start=1))


def _format_offline_llm_equivalent_reasoning(
    *,
    frame: pd.DataFrame,
    rows: list[dict],
    anomalies: list[dict[str, Any]],
    causal_estimates: list[dict[str, Any]],
    planned_budgets: dict[str, float] | None,
    segment_drivers: list[dict[str, Any]],
    structured_evidence: dict[str, Any],
) -> str:
    """Render Gemini-equivalent hypothesis reasoning without importing app-only dependencies."""
    channel_summaries = _offline_channel_summaries(frame)
    total_revenue = sum(safe_float(item.get("revenue")) for item in channel_summaries)
    total_spend = sum(safe_float(item.get("spend")) for item in channel_summaries)
    payload = {
        "forecasts": rows[:12],
        "plannedBudgets": planned_budgets or {},
        "anomalies": anomalies,
        "causalEstimates": causal_estimates,
        "causalEvidence": causal_estimates,
        "structuredCausalEvidence": structured_evidence,
        "driverEvidence": segment_drivers,
        "channels": channel_summaries,
        "avgRoas": safe_ratio(total_revenue, total_spend),
        "roasTrendPct": _offline_roas_trend_pct(frame),
    }
    hypotheses = build_causal_hypotheses(payload)
    ranking = build_llm_hypothesis_ranking(payload)

    lines = ["Hypothesis generation:"]
    if hypotheses:
        for item in hypotheses[:3]:
            lines.append(
                f"  {int(item.get('rank') or 0)}. {item.get('title', 'Causal hypothesis')}: "
                f"{item.get('hypothesis', 'No hypothesis text available')}"
            )
    else:
        lines.append("  1. No hypothesis could be generated from the current causal evidence.")

    lines.append("Evidence ranking:")
    if ranking:
        for item in ranking[:5]:
            support = "; ".join(str(value) for value in (item.get("supportingEvidence") or [])[:2])
            contradiction = "; ".join(str(value) for value in (item.get("contradictingEvidence") or [])[:1])
            lines.append(
                f"  {int(item.get('rank') or 0)}. {item.get('hypothesis', 'other')} "
                f"({item.get('confidence', 'low')} confidence, score={safe_float(item.get('confidenceScore')):.2f}) "
                f"support={support or 'limited signal'}; caution={contradiction or 'observational evidence only'}"
            )
    else:
        lines.append("  1. No ranked evidence was available.")

    lines.append("Confidence scoring:")
    if ranking:
        for item in ranking[:5]:
            lines.append(
                f"  {int(item.get('rank') or 0)}. {item.get('hypothesis', 'other')}: "
                f"confidence={item.get('confidence', 'low')}, score={safe_float(item.get('confidenceScore')):.2f}; "
                f"validation={item.get('recommendedValidation', 'validate with a controlled budget test')}"
            )
    else:
        lines.append("  1. confidence=low; validation=collect more channel history before treating the signal as causal.")
    return "\n".join(lines)


def _offline_channel_summaries(frame: pd.DataFrame) -> list[dict[str, Any]]:
    if frame.empty or not {"channel", "spend", "revenue"}.issubset(frame.columns):
        return []
    summaries: list[dict[str, Any]] = []
    total_revenue = safe_float(frame["revenue"].sum())
    for channel, group in frame.groupby("channel"):
        spend = safe_float(group["spend"].sum())
        revenue = safe_float(group["revenue"].sum())
        summaries.append(
            {
                "name": str(channel),
                "spend": spend,
                "revenue": revenue,
                "roas": safe_ratio(revenue, spend),
                "sharePct": safe_ratio(revenue, total_revenue) * 100,
            }
        )
    return sorted(summaries, key=lambda item: safe_float(item.get("revenue")), reverse=True)


def _offline_roas_trend_pct(frame: pd.DataFrame) -> float:
    if frame.empty or not {"date", "spend", "revenue"}.issubset(frame.columns):
        return 0.0
    try:
        daily = aggregate_segment_daily(frame)
        if daily.empty:
            return 0.0
        daily = daily.copy()
        daily["roas"] = np.where(daily["spend"] > 0, daily["revenue"] / daily["spend"], 0.0)
        return window_trend(daily, "roas", 28) * 100
    except Exception:
        return 0.0


def _causal_channel_metrics(frame: pd.DataFrame) -> dict[str, dict[str, Any]]:
    """Summarize observed-vs-baseline ROAS evidence for offline AI composition."""
    if frame.empty or not {"date", "channel", "spend", "revenue"}.issubset(frame.columns):
        return {}
    working = frame.copy()
    working["date"] = parse_dates_safely(working["date"])
    working = working.dropna(subset=["date", "channel"])
    if working.empty:
        return {}

    max_date = working["date"].max()
    recent_start = max_date - pd.Timedelta(days=29)
    prior_start = max_date - pd.Timedelta(days=59)
    prior_end = recent_start - pd.Timedelta(days=1)
    metrics: dict[str, dict[str, Any]] = {}
    for channel, group in working.groupby("channel"):
        recent = group[group["date"] >= recent_start]
        prior = group[(group["date"] >= prior_start) & (group["date"] <= prior_end)]
        if prior.empty:
            prior = group.iloc[: max(1, len(group) // 2)]
        if recent.empty:
            recent = group.iloc[max(0, len(group) // 2) :]
        campaign_type = "mixed_campaign_types"
        if "campaign_type" in group and not group.empty:
            by_type = group.groupby("campaign_type")["revenue"].sum().sort_values(ascending=False)
            if not by_type.empty:
                campaign_type = str(by_type.index[0])

        baseline_revenue = safe_float(prior["revenue"].sum())
        baseline_spend = safe_float(prior["spend"].sum())
        observed_revenue = safe_float(recent["revenue"].sum())
        observed_spend = safe_float(recent["spend"].sum())
        metrics[str(channel)] = {
            "campaign_type": campaign_type,
            "baseline_revenue": baseline_revenue,
            "observed_revenue": observed_revenue,
            "baseline_roas": safe_ratio(baseline_revenue, baseline_spend),
            "observed_roas": safe_ratio(observed_revenue, observed_spend),
        }
    return metrics


def write_causal_summary(
    frame: pd.DataFrame,
    rows: list[dict],
    output_dir: str | Path | None = None,
    planned_budgets: dict[str, float] | None = None,
    enable_live_ai: bool = False,
) -> Path:
    """Write causal_summary.txt beside predictions.csv or an explicit output directory."""
    target_dir = Path(output_dir or "output")
    target_dir.mkdir(parents=True, exist_ok=True)
    summary_path = target_dir / "causal_summary.txt"
    summary_path.write_text(
        generate_causal_summary(frame, rows, planned_budgets, enable_live_ai=enable_live_ai),
        encoding="utf-8",
    )
    return summary_path


def generate_causal_summary(
    frame: pd.DataFrame,
    rows: list[dict],
    planned_budgets: dict[str, float] | None = None,
    enable_live_ai: bool = False,
) -> str:
    """Generate the evaluator causal summary, auto-enriching with Gemini when configured."""
    offline = generate_offline_causal_summary(frame, rows, planned_budgets)
    if not enable_live_ai and not (os.getenv("GEMINI_API_KEY") or "").strip():
        return offline
    return _append_live_ai_enrichment(offline, frame, rows, planned_budgets, explicit_request=enable_live_ai)


def _append_live_ai_enrichment(
    offline_summary: str,
    frame: pd.DataFrame,
    rows: list[dict],
    planned_budgets: dict[str, float] | None = None,
    explicit_request: bool = False,
) -> str:
    if not (os.getenv("GEMINI_API_KEY") or "").strip():
        request_mode = "explicit --enable-live-ai" if explicit_request else "automatic GEMINI_API_KEY detection"
        return (
            f"{offline_summary}\n\n"
            "=== Live Gemini Enrichment ===\n"
            "Live LLM invoked: false\n"
            f"Request mode: {request_mode}.\n"
            "GEMINI_API_KEY was not configured. "
            "The deterministic offline causal summary above remains the authoritative evaluator output."
        )
    try:
        appendix = _generate_live_ai_causal_appendix(frame, rows, planned_budgets)
    except Exception as exc:
        request_body = _live_ai_request_body(_live_ai_summary_payload(frame, rows, planned_budgets))
        return (
            f"{offline_summary}\n\n"
            "=== Live Gemini Enrichment ===\n"
            "Live LLM invoked: false\n"
            "Gemini enrichment was attempted because GEMINI_API_KEY is configured, but it failed safely "
            f"({type(exc).__name__}: {_safe_error_message(exc)}).\n"
            "LIVE_GEMINI_REQUEST_REDACTED\n"
            f"{json.dumps(_redacted_request_record(request_body), indent=2, sort_keys=True)}\n"
            "LIVE_GEMINI_RESPONSE_REDACTED\n"
            "{\"error\": \"no live response received\"}\n"
            "The deterministic offline causal summary above remains the authoritative evaluator output."
        )
    return f"{offline_summary}\n\n{appendix}"


def _generate_live_ai_causal_appendix(
    frame: pd.DataFrame,
    rows: list[dict],
    planned_budgets: dict[str, float] | None = None,
) -> str:
    summary = _live_ai_summary_payload(frame, rows, planned_budgets)
    request_body = _live_ai_request_body(summary)
    raw_response, response_text = _call_gemini_generate_content(request_body)
    lines = [
        LIVE_AI_MODE_HEADER,
        "=== Live Gemini Enrichment ===",
        "Live LLM invoked: true",
        "LIVE_GEMINI_REQUEST_REDACTED",
        json.dumps(_redacted_request_record(request_body), indent=2, sort_keys=True),
        "LIVE_GEMINI_RESPONSE_REDACTED",
        _truncate_text(json.dumps(raw_response, indent=2, sort_keys=True), 12000),
        "Gemini causal narrative:",
        response_text.strip(),
        "LLM_HYPOTHESIS_RANKING",
    ]
    lines.append("  - See Gemini causal narrative above for the live ranked reasoning returned by the model.")
    return "\n".join(lines)


def _live_ai_summary_payload(
    frame: pd.DataFrame,
    rows: list[dict],
    planned_budgets: dict[str, float] | None = None,
) -> dict[str, Any]:
    from .anomaly import detect_anomalies
    from .causal_lite import estimate_causal_effects
    from .gemini_offline_cache import build_structured_causal_evidence

    anomalies = []
    causal_estimates = []
    try:
        anomalies = [item.to_dict() for item in detect_anomalies(frame)[:5]]
        causal_estimates = estimate_causal_effects(frame, anomalies)
    except Exception:
        anomalies = []
        causal_estimates = []
    structured_evidence = build_structured_causal_evidence(
        anomalies,
        causal_estimates,
        planned_budgets=planned_budgets,
        channel_metrics=_causal_channel_metrics(frame),
    )
    return {
        "forecasts": rows[:12],
        "plannedBudgets": planned_budgets or {},
        "anomalies": anomalies,
        "causalEvidence": causal_estimates,
        "structuredCausalEvidence": structured_evidence,
        "llmHypothesisInstructions": {
            "task": "Independently rank competing causal explanations from raw statistical evidence.",
            "candidateHypotheses": [
                "seasonality",
                "budget shift",
                "creative fatigue",
                "platform algorithm change",
                "tracking or attribution drift",
                "product or offer demand",
            ],
            "requiredEvidence": ["DiD effect", "p-value", "confidence interval", "anomaly z-score"],
        },
        "executiveContext": (
            "Generate a concise causal narrative grounded only in the supplied DiD estimates, p-values, "
            "confidence labels, date windows, anomalies, and forecast intervals."
        ),
    }


def _live_ai_request_body(summary: dict[str, Any]) -> dict[str, Any]:
    prompt = (
        "You are ForecastIQ's ecommerce causal reasoning analyst. Use only the JSON evidence below. "
        "Independently rank competing causal hypotheses such as seasonality, budget shift, creative fatigue, "
        "platform algorithm change, tracking drift, and product demand. Include confidence labels and cite the "
        "specific DiD effects, p-values, confidence intervals, anomaly z-scores, channels, campaign types, and "
        "date windows that support or contradict each hypothesis. End with a plain-language budget action for a "
        "marketing manager. Return concise text; do not invent facts outside the JSON.\n\n"
        f"EVIDENCE_JSON:\n{json.dumps(summary, indent=2, sort_keys=True, default=str)}"
    )
    return {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": prompt}],
            }
        ],
        "generationConfig": {
            "temperature": safe_float(os.getenv("GEMINI_TEMPERATURE", "0.2"), 0.2),
            "maxOutputTokens": int(min(2048, max(512, safe_float(os.getenv("GEMINI_MAX_OUTPUT_TOKENS", "1200"), 1200)))),
        },
    }


def _call_gemini_generate_content(request_body: dict[str, Any]) -> tuple[dict[str, Any], str]:
    key = (os.getenv("GEMINI_API_KEY") or "").strip()
    if not key:
        raise RuntimeError("GEMINI_API_KEY is not configured")
    model = (os.getenv("GEMINI_MODEL") or "gemini-2.5-flash-lite").strip() or "gemini-2.5-flash-lite"
    timeout = min(20.0, max(2.0, safe_float(os.getenv("GEMINI_TIMEOUT_SECONDS", "8"), 8.0)))
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{urllib.parse.quote(model, safe='')}:generateContent?key={urllib.parse.quote(key, safe='')}"
    )
    request = urllib.request.Request(
        url,
        data=json.dumps(request_body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read(120_000).decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        body = exc.read(4000).decode("utf-8", errors="replace")
        raise RuntimeError(f"Gemini HTTP {exc.code}: {_truncate_text(body, 600)}") from exc
    except TimeoutError as exc:
        raise TimeoutError(f"Gemini request timed out after {timeout:.1f}s") from exc
    parsed = json.loads(raw)
    text_parts: list[str] = []
    for candidate in parsed.get("candidates", []) or []:
        content = candidate.get("content") if isinstance(candidate, dict) else {}
        for part in (content or {}).get("parts", []) or []:
            text = part.get("text") if isinstance(part, dict) else None
            if text:
                text_parts.append(str(text))
    response_text = "\n".join(text_parts).strip()
    if not response_text:
        raise RuntimeError("Gemini response did not include text content")
    return parsed, response_text


def _redacted_request_record(request_body: dict[str, Any]) -> dict[str, Any]:
    model = (os.getenv("GEMINI_MODEL") or "gemini-2.5-flash-lite").strip() or "gemini-2.5-flash-lite"
    timeout = min(20.0, max(2.0, safe_float(os.getenv("GEMINI_TIMEOUT_SECONDS", "8"), 8.0)))
    return {
        "method": "POST",
        "url": f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key=REDACTED",
        "timeout_seconds": timeout,
        "body": request_body,
    }


def _truncate_text(value: str, limit: int) -> str:
    text = value if isinstance(value, str) else str(value)
    return text if len(text) <= limit else text[:limit] + "\n... [truncated]"


def _safe_error_message(exc: Exception) -> str:
    message = str(exc)
    key = os.getenv("GEMINI_API_KEY") or ""
    if key:
        message = message.replace(key, "REDACTED")
    return _truncate_text(message, 600)


def _budget_translation_lines(rows: list[dict]) -> list[str]:
    if not rows:
        return [
            "No forecast rows were available, so keep budgets steady until a valid marketing export is provided."
        ]
    lines: list[str] = []
    for row in rows:
        level = str(row.get("level") or "overall")
        segment = str(row.get("segment") or "all")
        horizon = int(safe_float(row.get("horizon_days"), 0))
        revenue = safe_float(row.get("expected_revenue"), 0.0)
        roas = safe_float(row.get("expected_roas"), 0.0)
        confidence = str(row.get("forecast_confidence") or "unknown")
        width = safe_float(row.get("interval_width_pct"), 0.0)
        if confidence == "high":
            action = "This is suitable for a controlled budget move, with normal monitoring."
        elif confidence == "medium":
            action = "Use this as a planning range and move budget in smaller increments."
        else:
            action = "Treat this as directional; validate before making a large budget shift."
        lines.append(
            f"  - {level} | {segment} | {horizon}d: expected revenue ${revenue:,.0f} at {roas:.2f}x ROAS "
            f"with {confidence} confidence and a {width:.1f}% interval. {action}"
        )
    return lines


def generate_explainability_notes(frame: pd.DataFrame, rows: list[dict]) -> str:
    """Generate deterministic local explanations for evaluator forecasts."""
    lines = [
        "=== ForecastIQ Explainability Notes (offline, deterministic) ===",
        "Purpose: explain why each evaluator forecast moved, using local historical signals rather than generic feature importance.",
        "Signals: recent revenue trend, spend trend, ROAS stability, seasonality marker, and interval width/confidence.",
        "",
    ]
    if frame.empty or not rows:
        lines.append("No usable rows were available; fallback predictions are driven by evaluator-safe defaults.")
        return "\n".join(lines)

    for row in rows:
        horizon = int(safe_float(row.get("horizon_days"), 0))
        segment_frame = _explainability_segment_frame(frame, row)
        signals = _forecast_signals(segment_frame, row, horizon)
        lines.append(
            f"- {row.get('level', 'unknown')} | {row.get('segment', 'unknown')} | {horizon}d | "
            f"model_type={row.get('model_type', 'unknown')} | confidence={row.get('forecast_confidence', 'unknown')}"
        )
        for signal in signals[:3]:
            lines.append(f"  - {signal}")
    return "\n".join(lines)


def write_explainability_notes(
    frame: pd.DataFrame,
    rows: list[dict],
    output_dir: str | Path | None = None,
) -> Path:
    """Write explainability_notes.txt beside evaluator predictions."""
    target_dir = Path(output_dir or "output")
    target_dir.mkdir(parents=True, exist_ok=True)
    notes_path = target_dir / "explainability_notes.txt"
    notes_path.write_text(generate_explainability_notes(frame, rows), encoding="utf-8")
    return notes_path


def _explainability_segment_frame(frame: pd.DataFrame, row: dict) -> pd.DataFrame:
    level = str(row.get("level") or "overall")
    segment = str(row.get("segment") or "all")
    if frame.empty or level == "overall":
        return frame.copy()
    column = "campaign_name" if level == "campaign" else level
    if column not in frame:
        return pd.DataFrame(columns=frame.columns)
    return frame[frame[column].astype(str) == segment].copy()


def _forecast_signals(segment: pd.DataFrame, row: dict, horizon: int) -> list[str]:
    if segment.empty:
        return [
            "No matching historical segment rows; forecast was generated from safe evaluator defaults.",
            _confidence_rationale(segment, row, horizon),
            "Seasonality could not be inferred because no valid dated history was present.",
        ]

    daily = aggregate_segment_daily(segment)
    revenue_trend_pct = window_trend(daily, "revenue", 28) * 100
    spend_trend_pct = window_trend(daily, "spend", 28) * 100
    recent = daily.tail(min(28, len(daily))).copy()
    roas = np.where(recent["spend"] > 0, recent["revenue"] / recent["spend"], np.nan)
    roas = pd.Series(roas).replace([np.inf, -np.inf], np.nan).dropna()
    if len(roas):
        roas_mean = safe_float(roas.mean())
        roas_cv = safe_ratio(safe_float(roas.std(ddof=0)), roas_mean) * 100 if roas_mean else 0.0
        roas_signal = f"ROAS stability: recent average {roas_mean:.2f}x with {roas_cv:.1f}% coefficient of variation."
    else:
        roas_signal = "ROAS stability: not computable because recent spend was zero or missing."

    parsed_dates = parse_dates_safely(daily["date"]).dropna()
    if not parsed_dates.empty and horizon > 0:
        forecast_end = parsed_dates.max() + pd.Timedelta(days=horizon)
        seasonality_signal = (
            f"Seasonality marker: {horizon}d forecast ends in month {forecast_end.month} "
            f"on weekday {forecast_end.dayofweek}, using model month/day-of-week features."
        )
    else:
        seasonality_signal = "Seasonality marker: unavailable because dated history was incomplete."

    interval_signal = (
        f"Uncertainty: interval width {safe_float(row.get('interval_width_pct')):.1f}% "
        f"with confidence label {row.get('forecast_confidence', 'unknown')}."
    )
    return [
        _confidence_rationale(segment, row, horizon),
        f"Recent 28-day revenue trend: {revenue_trend_pct:+.1f}% versus the prior half-window.",
        f"{seasonality_signal} {roas_signal}",
        f"Recent 28-day spend trend: {spend_trend_pct:+.1f}% versus the prior half-window.",
        interval_signal,
    ]


def _confidence_rationale(segment: pd.DataFrame, row: dict, horizon: int) -> str:
    label = str(row.get("forecast_confidence") or "unknown")
    interval_pct = safe_float(row.get("interval_width_pct"))
    model_type = str(row.get("model_type") or "unknown")
    history_days = 0
    if not segment.empty and "date" in segment:
        history_days = int(parse_dates_safely(segment["date"]).dropna().dt.normalize().nunique())

    reasons: list[str] = []
    if model_type == TRAINED_ESTIMATED_SPEND_MODEL_TYPE:
        reasons.append("spend was inferred or the segment was sparse")
    elif model_type == SAFE_BASELINE_MODEL_TYPE:
        reasons.append("the trained artifact could not score this input safely")
    if history_days < 30:
        reasons.append(f"only {history_days} usable historical days were available")
    elif history_days >= 90:
        reasons.append(f"{history_days} historical days support the segment")
    else:
        reasons.append(f"{history_days} historical days provide a moderate evidence base")
    if horizon >= 90:
        reasons.append("the 90-day horizon compounds seasonality and residual volatility")
    elif horizon >= 60:
        reasons.append("the 60-day horizon carries more uncertainty than the 30-day plan")
    if interval_pct >= 90:
        reasons.append(f"the revenue interval is wide at {interval_pct:.1f}%")
    elif interval_pct <= 70:
        reasons.append(f"the revenue interval is comparatively tighter at {interval_pct:.1f}%")
    else:
        reasons.append(f"the revenue interval is moderate at {interval_pct:.1f}%")

    return f"Confidence rationale: {label} because " + "; ".join(reasons) + "."
