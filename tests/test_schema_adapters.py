from __future__ import annotations

import math
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from backend.data_preprocessing import validate_records
from backend.predict import build_predictions, canonicalize_frame, read_csv_folder, safe_load_model
from backend.schema_adapters import normalize_marketing_frame


class SchemaAdapterTests(unittest.TestCase):
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
