"""Evaluator-safe CSV loading, model loading, output writing, and causal summaries."""

from __future__ import annotations

import csv
import os
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd

from .schema_adapters import (
    CANONICAL_COLUMNS,
    COLUMN_ALIASES,
    SOURCE_FILE_COLUMN,
    SOURCE_SCHEMA_COLUMN,
    alias_index,
    channel_from_source_file,
    normalize_marketing_frame,
    reconcile_normalized_frames,
)
from .evaluator_contract import (
    ARTIFACT_TYPE,
    ARTIFACT_VERSION,
    HORIZONS,
    MAX_MODEL_ARTIFACT_BYTES,
    OUTPUT_COLUMNS,
    SAFE_BASELINE_MODEL_TYPE,
    TRAINED_MODEL_TYPE,
    CleanResult,
    empty_frame,
    log,
    safe_float,
)
from .evaluator_intervals import DEFAULT_HORIZON_CONFIDENCE_Z
from .segment_utils import FEATURE_COLUMNS, safe_ratio, window_trend

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
        frame[column] = pd.to_numeric(series_for(column, 0), errors="coerce")
        invalid = frame[column].isna() | ~np.isfinite(frame[column])
        if invalid.any():
            issues.append(f"{int(invalid.sum())} invalid numeric values in '{column}' replaced with 0")
            frame.loc[invalid, column] = 0.0

    parsed_dates = pd.to_datetime(frame["date"], errors="coerce")
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

        model_sklearn = "1.9.0"
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
            log(f"{sklearn_mismatch_warning}; functional smoke test failed, using safe baseline")
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
        return (
            "=== ForecastIQ Causal Summary (offline, deterministic) ===\n"
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
            event_date = pd.to_datetime(item.get("date"), errors="coerce")
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
            direction = "rose" if effect >= 0 else "fell"
            causal_lines.append(
                "  - {channel} on {date}: incremental revenue ${effect:,.0f} "
                "(95% CI ${lower:,.0f} to ${upper:,.0f}), ROAS effect {roas:.2f}x, "
                "confidence={confidence}. Pre window: {pre_window}; post window: {post_window}. "
                "{channel} revenue {direction} after the detected event on {date}, compared with "
                "movement in control channels, suggesting the event had observable impact while "
                "still requiring an experiment for proof.".format(
                    channel=channel,
                    date=event_label,
                    effect=effect,
                    lower=lower,
                    upper=upper,
                    roas=roas,
                    confidence=confidence,
                    pre_window=pre_window,
                    post_window=post_window,
                    direction=direction,
                )
            )
    else:
        causal_lines = ["  - No causal estimate available; history was too sparse around detected events."]

    spend_trend = window_trend(daily, "spend", 28)
    revenue_trend_val = window_trend(daily, "revenue", 28)

    overall_30 = next(
        (r for r in rows if r["level"] == "overall" and int(r["horizon_days"]) == 30), {}
    )
    forecast_rev_30 = safe_float(overall_30.get("expected_revenue", 0))
    forecast_roas_30 = safe_float(overall_30.get("expected_roas", 0))

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
        ) + "."

    lines = [
        "=== ForecastIQ Causal Summary (offline, deterministic) ===",
        executive_interpretation,
        f"Historical period: {daily['date'].iloc[0]} to {daily['date'].iloc[-1]} ({len(daily)} days)",
        f"Total spend: ${total_spend:,.0f} | Total revenue: ${total_revenue:,.0f} | Blended ROAS: {blended_roas:.2f}x",
        f"Performance is {trend_note}.",
        *([planned_budget_note] if planned_budget_note else []),
        f"Leading channel by ROAS: {top_channel} at {top_roas:.2f}x - "
        "likely driven by stronger conversion quality or lower CPC in this channel.",
        f"Leading channel by revenue: {top_revenue_channel}; highest-risk channel by ROAS: "
        f"{weakest_channel} at {weakest_roas:.2f}x.",
        f"30-day forecast: expected revenue ${forecast_rev_30:,.0f} at {forecast_roas_30:.2f}x ROAS.",
        "Anomaly signals (top 3, used as forecast evidence):",
        *anomaly_lines,
        "Causal effect estimates (observational DiD, not experimental incrementality):",
        *causal_lines,
        f"Causal hypothesis: the {len(top_anomalies)} anomaly signal(s) above, combined "
        "with spend trajectory and channel ROAS efficiency, are the observable evidence "
        "base for the forecast range. Wider intervals at 60 and 90 days reflect compounding "
        "uncertainty from these detected signals and auction dynamics.",
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

    # Optional: attempt to enrich the summary with an LLM call.
    # This is intentionally last and completely optional - the evaluator
    # still returns the deterministic summary if the call fails.
    _gemini_api_key = None
    try:
        import os

        _gemini_api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    except Exception:
        pass

    if _gemini_api_key:
        try:
            import google.genai as genai

            _client = genai.Client(api_key=_gemini_api_key)
            _prompt = (
                "You are a senior ecommerce marketing analyst. Based on the following data-grounded "
                "forecast summary, write ONE additional paragraph (max 80 words) identifying the "
                "single most important strategic action for the next 30 days. Be specific and direct.\n\n"
                + "\n".join(lines[:10])
            )
            _response = _client.models.generate_content(
                model=os.environ.get("GEMINI_MODEL", "gemini-2.5-flash"),
                contents=_prompt,
            )
            _ai_paragraph = (_response.text or "").strip()
            if _ai_paragraph:
                lines.append("")
                lines.append("=== AI Strategic Recommendation (Gemini) ===")
                lines.append(_ai_paragraph)
        except Exception as _exc:
            lines.append("")
            lines.append("=== AI Strategic Recommendation (Gemini) ===")
            lines.append(
                f"[Gemini enrichment could not complete ({type(_exc).__name__}). "
                "The predictions.csv evaluator contract is unaffected. "
                "Re-run with a valid GEMINI_API_KEY to enable live strategic recommendations.]"
            )
    else:
        lines.append("")
        lines.append("=== AI Strategic Recommendation ===")
        lines.append(
            f"Offline recommendation: prioritize {top_channel}, the strongest ROAS channel, while "
            f"tightening {weakest_channel}, the highest-risk channel in this dataset. Keep the next "
            "budget move small enough to validate inside the 30-day forecast band before using the "
            "wider 60 and 90-day planning ranges. Live Gemini enrichment is optional and does not "
            "affect predictions.csv."
        )

    return "\n".join(lines)


def write_causal_summary(
    frame: pd.DataFrame,
    rows: list[dict],
    output_dir: str | Path | None = None,
    planned_budgets: dict[str, float] | None = None,
) -> Path:
    """Write causal_summary.txt beside predictions.csv or an explicit output directory."""
    target_dir = Path(output_dir or "output")
    target_dir.mkdir(parents=True, exist_ok=True)
    summary_path = target_dir / "causal_summary.txt"
    summary_path.write_text(
        generate_offline_causal_summary(frame, rows, planned_budgets),
        encoding="utf-8",
    )
    return summary_path
