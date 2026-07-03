from __future__ import annotations

import numpy as np
import pandas as pd

from backend.evaluator_io import canonicalize_frame, read_csv_folder, safe_load_model
from backend.inference import build_predictions


def _assert_schema_safe(rows: list[dict]) -> None:
    assert rows
    for row in rows:
        for column in [
            "expected_revenue",
            "lower_revenue",
            "upper_revenue",
            "expected_roas",
            "lower_roas",
            "upper_roas",
            "interval_width_pct",
        ]:
            value = float(row[column])
            assert np.isfinite(value), f"{column} was not finite in {row}"
            assert value >= 0, f"{column} was negative in {row}"


def test_negative_spend_revenue_and_non_numeric_values_are_cleaned_without_nan() -> None:
    raw = pd.DataFrame(
        {
            "date": ["2026-01-01", "2026-01-02", "2026-01-03"],
            "channel": ["Google Ads", "Meta Ads", "Microsoft Ads"],
            "campaign_type": ["Search", "Paid Social", "Search"],
            "campaign_name": ["Brand", "Prospecting", "Bing"],
            "spend": [-100, "not numeric", 80],
            "clicks": ["bad", 20, 15],
            "impressions": [1000, "oops", 900],
            "conversions": [5, "bad", 3],
            "revenue": [500, -10, "not numeric"],
        }
    )

    cleaned = canonicalize_frame(raw)
    rows = build_predictions(cleaned.frame, safe_load_model("missing-model.pkl"))

    assert any("negative spend" in issue for issue in cleaned.issues)
    assert any("negative revenue" in issue for issue in cleaned.issues)
    assert any("invalid spend values" in issue for issue in cleaned.issues)
    assert any("invalid revenue values" in issue for issue in cleaned.issues)
    _assert_schema_safe(rows)


def test_missing_required_columns_and_currency_locale_values_fail_safe() -> None:
    raw = pd.DataFrame(
        {
            "Day": ["2026-01-01", "bad-date", "2026-01-03"],
            "Campaign": ["Brand", "Prospecting", "Shopping"],
            "Cost": ["$1,234.56", "1.234,56", "250"],
            "Sales": ["$5,432.10", "2.345,67", "bad"],
        }
    )

    cleaned = canonicalize_frame(raw)
    rows = build_predictions(cleaned.frame, safe_load_model("missing-model.pkl"))

    assert cleaned.total_rows == 3
    assert any("invalid spend values" in issue for issue in cleaned.issues)
    assert any("invalid revenue values" in issue for issue in cleaned.issues)
    assert any("malformed or missing dates" in issue for issue in cleaned.issues)
    _assert_schema_safe(rows)


def test_multi_source_duplicate_revenue_guard_prevents_blind_double_counting(tmp_path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "shopify_orders.csv").write_text(
        "created_at,total_price,orders,product_type\n"
        "2026-01-01,1000,10,Shoes\n"
        "2026-01-02,1100,11,Shoes\n",
        encoding="utf-8",
    )
    (data_dir / "ga4_events.csv").write_text(
        "event_date,sessionSource,sessionMedium,purchaseRevenue,sessions,conversions\n"
        "2026-01-01,google,cpc,1000,200,10\n"
        "2026-01-02,google,cpc,1100,220,11\n",
        encoding="utf-8",
    )
    (data_dir / "google_ads.csv").write_text(
        "segments_date,campaign_name,metrics_cost_micros,metrics_clicks,metrics_impressions,metrics_conversions,metrics_conversions_value\n"
        "2026-01-01,Brand,500000000,60,2000,10,1000\n"
        "2026-01-02,Brand,550000000,66,2200,11,1100\n",
        encoding="utf-8",
    )

    raw = read_csv_folder(data_dir)
    cleaned = canonicalize_frame(raw)
    rows = build_predictions(cleaned.frame, safe_load_model("missing-model.pkl"))

    assert cleaned.valid_rows > 0
    assert float(cleaned.frame["revenue"].sum()) <= 4200
    assert any(str(schema).startswith("reconciled") for schema in raw["__source_schema"].unique())
    _assert_schema_safe(rows)
