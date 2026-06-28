from __future__ import annotations

import math
import shutil
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from backend.data_preprocessing import validate_records
from backend.predict import build_predictions, canonicalize_frame, read_csv_folder, safe_load_model
from backend.schema_adapters import SOURCE_SCHEMA_COLUMN, normalize_marketing_frame


class SchemaAdapterTests(unittest.TestCase):
    def assert_fixture_parses(self, name: str) -> None:
        expected_columns = [
            "date",
            "channel",
            "campaign_type",
            "campaign_name",
            "spend",
            "clicks",
            "impressions",
            "conversions",
            "revenue",
            "roas",
        ]
        raw = pd.read_csv(Path("data/fixtures") / name)
        adapted = normalize_marketing_frame(raw)

        self.assertEqual(list(adapted.frame.columns[: len(expected_columns)]), expected_columns)
        self.assertGreater(len(adapted.frame), 0)
        self.assertFalse(adapted.frame[expected_columns].empty)

    def test_ads_raw_fixture_parses_correctly(self) -> None:
        self.assert_fixture_parses("ads_raw_export.csv")

    def test_ga4_raw_fixture_parses_correctly(self) -> None:
        self.assert_fixture_parses("ga4_raw_export.csv")

    def test_shopify_raw_fixture_parses_correctly(self) -> None:
        self.assert_fixture_parses("shopify_raw_orders.csv")

    def test_ga4_export_normalizes_to_campaign_rows(self) -> None:
        raw = pd.DataFrame(
            {
                "date": ["2026-01-01", "2026-01-02"],
                "sessionSource": ["google", "facebook"],
                "sessionMedium": ["cpc", "paid_social"],
                "purchaseRevenue": [1200, 450],
                "sessions": [300, 120],
                "conversions": [12, 5],
            }
        )

        adapted = normalize_marketing_frame(raw)
        cleaned = canonicalize_frame(raw)

        self.assertEqual(adapted.schema_type, "ga4")
        self.assertEqual(cleaned.valid_rows, 2)
        self.assertEqual(set(cleaned.frame["channel"]), {"Google Ads", "Meta Ads"})
        self.assertEqual(float(cleaned.frame["spend"].sum()), 0.0)
        self.assertEqual(float(cleaned.frame["revenue"].sum()), 1650.0)

    def test_shopify_export_normalizes_missing_spend(self) -> None:
        raw = pd.DataFrame(
            {
                "created_at": ["2026-02-01T09:00:00Z", "2026-02-02T10:00:00Z"],
                "total_price": [220.5, 199.99],
                "orders": [1, 1],
                "product_type": ["Shoes", "Accessories"],
            }
        )

        cleaned = canonicalize_frame(raw)

        self.assertEqual(cleaned.valid_rows, 2)
        self.assertEqual(set(cleaned.frame["channel"]), {"Shopify"})
        self.assertTrue((cleaned.frame["spend"] == 0).all())
        self.assertEqual(float(cleaned.frame["conversions"].sum()), 2.0)

    def test_ads_export_uses_conversion_value_alias(self) -> None:
        raw = pd.DataFrame(
            {
                "date": ["2026-03-01", "2026-03-02"],
                "platform": ["Microsoft Ads", "Microsoft Ads"],
                "campaign": ["Bing Brand", "Bing Brand"],
                "advertising_channel_type": ["Search", "Search"],
                "cost": [100, 125],
                "clicks": [30, 40],
                "impressions": [1000, 1300],
                "conversions": [4, 5],
                "conversion_value": [640, 820],
            }
        )

        cleaned = canonicalize_frame(raw)

        self.assertEqual(cleaned.valid_rows, 2)
        self.assertEqual(set(cleaned.frame["channel"]), {"Microsoft Ads"})
        self.assertEqual(float(cleaned.frame["revenue"].sum()), 1460.0)
        self.assertTrue(math.isclose(float(cleaned.frame["roas"].mean()), 6.512, rel_tol=0.05))

    def test_google_ads_micros_are_scaled_to_account_currency(self) -> None:
        raw = pd.DataFrame(
            {
                "segments_date": ["2026-04-01", "2026-04-02"],
                "metrics_cost_micros": [123_450_000, 89_000_000],
                "metrics_clicks": [44, 30],
                "metrics_impressions": [2200, 1800],
                "metrics_conversions": [5.0, 3.0],
                "metrics_conversions_value": [700.0, 410.0],
                "campaign_advertising_channel_type": ["SEARCH", "SEARCH"],
                "campaign_name": ["Google Brand", "Google Nonbrand"],
            }
        )

        cleaned = canonicalize_frame(raw)

        self.assertEqual(cleaned.valid_rows, 2)
        self.assertTrue(math.isclose(float(cleaned.frame["spend"].sum()), 212.45, rel_tol=0.001))
        self.assertEqual(float(cleaned.frame["revenue"].sum()), 1110.0)
        self.assertEqual(set(cleaned.frame["campaign_type"]), {"SEARCH"})

    def test_microsoft_ads_export_column_names_are_supported(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            (data_dir / "microsoft_ads_performance.csv").write_text(
                "TimePeriod,CampaignName,CampaignType,Spend,Clicks,Impressions,Conversions,Revenue\n"
                "2026-05-01,Bing Brand,Search,51.25,18,900,2,310.5\n"
                "2026-05-02,Bing Brand,Search,64.75,23,1100,3,455.0\n",
                encoding="utf-8",
            )

            raw = read_csv_folder(data_dir)
            cleaned = canonicalize_frame(raw)

            self.assertEqual(cleaned.valid_rows, 2)
            self.assertEqual(set(cleaned.frame["channel"]), {"Microsoft Ads"})
            self.assertEqual(float(cleaned.frame["spend"].sum()), 116.0)
            self.assertEqual(float(cleaned.frame["revenue"].sum()), 765.5)

    def test_conflicting_duplicate_alias_columns_prefer_canonical_names(self) -> None:
        raw = pd.DataFrame(
            {
                "date": ["2026-07-01"],
                "day": ["1999-01-01"],
                "channel": ["Google Ads"],
                "platform": ["Meta Ads"],
                "campaign_type": ["Search"],
                "CampaignType": ["Shopping"],
                "campaign_name": ["Canonical Campaign"],
                "CampaignName": ["Alias Campaign"],
                "spend": [100.0],
                "cost": [999.0],
                "revenue": [500.0],
                "conversion_value": [9999.0],
            }
        )

        cleaned = canonicalize_frame(raw)

        self.assertEqual(cleaned.valid_rows, 1)
        row = cleaned.frame.iloc[0]
        self.assertEqual(row["date"], "2026-07-01")
        self.assertEqual(row["channel"], "Google Ads")
        self.assertEqual(row["campaign_type"], "Search")
        self.assertEqual(row["campaign_name"], "Canonical Campaign")
        self.assertEqual(float(row["spend"]), 100.0)
        self.assertEqual(float(row["revenue"]), 500.0)

    def test_all_optional_fields_missing_rows_are_filled_safely(self) -> None:
        raw = pd.DataFrame(
            {
                "date": ["2026-07-01", "2026-07-02"],
                "channel": ["Google Ads", "Meta Ads"],
                "campaign_name": ["Brand", "Prospecting"],
                "spend": [100.0, 50.0],
                "revenue": [450.0, 125.0],
            }
        )

        cleaned = canonicalize_frame(raw)

        self.assertEqual(cleaned.valid_rows, 2)
        for column in ["clicks", "impressions", "conversions"]:
            self.assertTrue((cleaned.frame[column] == 0).all())
        self.assertEqual(set(cleaned.frame["campaign_type"]), {"Unclassified"})
        self.assertTrue(math.isclose(float(cleaned.frame["roas"].iloc[0]), 4.5, rel_tol=0.001))

    def test_bing_timeperiod_campaigntype_campaignname_combination(self) -> None:
        raw = pd.DataFrame(
            {
                "TimePeriod": ["2026-08-01", "2026-08-02"],
                "CampaignType": ["Search", "Shopping"],
                "CampaignName": ["Bing Brand", "Bing Shopping"],
                "Spend": [25.0, 45.0],
                "Clicks": [10, 18],
                "Impressions": [400, 700],
                "Conversions": [2, 3],
                "Revenue": [120.0, 210.0],
            }
        )

        cleaned = canonicalize_frame(raw)

        self.assertEqual(cleaned.valid_rows, 2)
        self.assertEqual(set(cleaned.frame["channel"]), {"Microsoft Ads"})
        self.assertEqual(set(cleaned.frame["campaign_type"]), {"Search", "Shopping"})
        self.assertEqual(set(cleaned.frame["campaign_name"]), {"Bing Brand", "Bing Shopping"})

    def test_ga4_plus_ads_reconciles_revenue_without_double_counting(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            (data_dir / "ga4_export.csv").write_text(
                "date,sessionSource,sessionMedium,purchaseRevenue,sessions,conversions\n"
                "2026-06-01,google,cpc,600,1000,20\n"
                "2026-06-01,facebook,paid_social,400,800,12\n"
                "2026-06-02,google,cpc,660,1100,22\n"
                "2026-06-02,facebook,paid_social,440,850,13\n",
                encoding="utf-8",
            )
            (data_dir / "ads_export.csv").write_text(
                "date,platform,campaign,cost,clicks,impressions,conversions,conversion_value\n"
                "2026-06-01,Google Ads,Brand,120,80,5000,8,600\n"
                "2026-06-01,Meta Ads,Prospecting,75,55,4200,5,400\n"
                "2026-06-02,Google Ads,Brand,135,85,5300,9,660\n"
                "2026-06-02,Meta Ads,Prospecting,80,58,4400,6,440\n",
                encoding="utf-8",
            )

            raw = read_csv_folder(data_dir)
            cleaned = canonicalize_frame(raw)

            self.assertEqual(set(raw[SOURCE_SCHEMA_COLUMN]), {"reconciled_ga4_with_media"})
            self.assertTrue(math.isclose(float(cleaned.frame["revenue"].sum()), 2100.0, rel_tol=0.001))
            self.assertLess(float(cleaned.frame["revenue"].sum()), 2200.0)
            self.assertIn("Google Ads", set(cleaned.frame["channel"]))
            self.assertIn("Meta Ads", set(cleaned.frame["channel"]))

    def test_mixed_csv_folder_merges_source_schemas_safely(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            (data_dir / "ga4.csv").write_text(
                "date,sessionSource,sessionMedium,purchaseRevenue,sessions,conversions\n"
                "2026-01-01,google,cpc,1200,300,12\n",
                encoding="utf-8",
            )
            (data_dir / "shopify.csv").write_text(
                "created_at,total_price,orders,product_type\n"
                "2026-01-02T09:00:00Z,250,1,Shoes\n",
                encoding="utf-8",
            )
            (data_dir / "ads.csv").write_text(
                "date,platform,campaign,cost,clicks,impressions,conversions,conversion_value\n"
                "2026-01-03,Google Ads,Brand,100,40,1200,4,500\n",
                encoding="utf-8",
            )

            raw = read_csv_folder(data_dir)
            cleaned = canonicalize_frame(raw)
            rows = build_predictions(cleaned.frame, safe_load_model("missing-model.pkl"))

            self.assertEqual(cleaned.valid_rows, 3)
            self.assertIn("Shopify", set(cleaned.frame["channel"]))
            self.assertTrue(rows)
            self.assertEqual({row["horizon_days"] for row in rows}, {30, 60, 90})

    def test_overlapping_ga4_shopify_ads_revenue_is_not_double_counted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            dates = pd.date_range("2026-01-01", periods=5, freq="D").strftime("%Y-%m-%d")
            true_daily_revenue = [11000, 11500, 12000, 11800, 12500]
            total_truth = float(sum(true_daily_revenue))

            (data_dir / "ga4_sessions.csv").write_text(
                "date,sessionSource,sessionMedium,purchaseRevenue,sessions,conversions\n"
                + "\n".join(
                    f"{date},google,cpc,{revenue * 0.65},1000,40\n"
                    f"{date},facebook,paid_social,{revenue * 0.35},800,28"
                    for date, revenue in zip(dates, true_daily_revenue)
                ),
                encoding="utf-8",
            )
            (data_dir / "shopify_orders.csv").write_text(
                "created_at,total_price,orders,product_type\n"
                + "\n".join(
                    f"{date}T09:00:00Z,{revenue},50,All Products"
                    for date, revenue in zip(dates, true_daily_revenue)
                ),
                encoding="utf-8",
            )
            (data_dir / "ads_export.csv").write_text(
                "date,platform,campaign,cost,clicks,impressions,conversions,conversion_value\n"
                + "\n".join(
                    f"{date},Google Ads,Brand,{revenue * 0.08},200,5000,30,{revenue * 0.65}\n"
                    f"{date},Meta Ads,Prospecting,{revenue * 0.06},160,6000,22,{revenue * 0.35}"
                    for date, revenue in zip(dates, true_daily_revenue)
                ),
                encoding="utf-8",
            )

            raw = read_csv_folder(data_dir)
            cleaned = canonicalize_frame(raw)

            self.assertGreater(cleaned.valid_rows, 0)
            self.assertTrue(math.isclose(float(cleaned.frame["revenue"].sum()), total_truth, rel_tol=0.01))
            self.assertLess(float(cleaned.frame["revenue"].sum()), total_truth * 1.05)
            self.assertIn("Google Ads", set(cleaned.frame["channel"]))
            self.assertIn("Meta Ads", set(cleaned.frame["channel"]))

    def test_raw_fixture_folder_with_ga4_shopify_and_ads_reconciles_once(self) -> None:
        fixture_dir = Path("data/fixtures")
        expected_revenue = pd.read_csv(fixture_dir / "shopify_raw_orders.csv")["total_price"].sum()

        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            for name in ["ga4_raw_export.csv", "shopify_raw_orders.csv", "ads_raw_export.csv"]:
                shutil.copyfile(fixture_dir / name, data_dir / name)

            raw = read_csv_folder(data_dir)
            cleaned = canonicalize_frame(raw)

            self.assertGreater(cleaned.valid_rows, 0)
            self.assertTrue(math.isclose(float(cleaned.frame["revenue"].sum()), float(expected_revenue), rel_tol=0.01))
            self.assertLess(float(cleaned.frame["revenue"].sum()), float(expected_revenue) * 1.05)
            self.assertEqual(set(raw[SOURCE_SCHEMA_COLUMN]), {"reconciled_shopify_with_media"})
            self.assertIn("Google Ads", set(cleaned.frame["channel"]))
            self.assertIn("Meta Ads", set(cleaned.frame["channel"]))

    def test_real_drive_ads_column_shapes_are_supported(self) -> None:
        google = pd.DataFrame(
            {
                "segments_date": ["2024-01-01"],
                "metrics_clicks": [158],
                "metrics_conversions": [4.2],
                "metrics_cost_micros": [46_980_000],
                "metrics_impressions": [481],
                "metrics_conversions_value": [549.99],
                "campaign_advertising_channel_type": ["SEARCH"],
                "campaign_name": ["Search_TM_Campaign_01"],
            }
        )
        meta = pd.DataFrame(
            {
                "date_start": ["2024-05-23"],
                "cpc": [12.1],
                "spend": [85.0],
                "clicks": [37],
                "impressions": [5188],
                "conversion": [183.0],
                "campaign_name": ["Generic_Campaign_02"],
            }
        )
        bing = pd.DataFrame(
            {
                "TimePeriod": ["2024-05-25"],
                "Revenue": [100.0],
                "Spend": [4.7],
                "Clicks": [22],
                "Impressions": [140],
                "Conversions": [2.0],
                "CampaignType": ["Search"],
                "CampaignName": ["Search_TM_Campaign_02"],
            }
        )

        google_clean = canonicalize_frame(google).frame
        meta_clean = canonicalize_frame(meta).frame
        bing_clean = canonicalize_frame(bing).frame

        self.assertEqual(google_clean.iloc[0]["date"], "2024-01-01")
        self.assertTrue(math.isclose(float(google_clean.iloc[0]["spend"]), 46.98, rel_tol=0.001))
        self.assertEqual(float(google_clean.iloc[0]["revenue"]), 549.99)
        self.assertEqual(meta_clean.iloc[0]["date"], "2024-05-23")
        self.assertEqual(float(meta_clean.iloc[0]["revenue"]), 183.0)
        self.assertEqual(bing_clean.iloc[0]["date"], "2024-05-25")
        self.assertEqual(bing_clean.iloc[0]["campaign_name"], "Search_TM_Campaign_02")

    def test_api_validation_accepts_ga4_records(self) -> None:
        records = [
            {
                "date": "2026-01-01",
                "sessionSource": "google",
                "sessionMedium": "cpc",
                "purchaseRevenue": 1200,
                "sessions": 300,
                "conversions": 12,
            }
        ]

        frame, validation = validate_records(records)

        self.assertEqual(validation.validRows, 1)
        self.assertFalse(frame.empty)
        self.assertEqual(frame.iloc[0]["channel"], "Google Ads")


if __name__ == "__main__":
    unittest.main()
