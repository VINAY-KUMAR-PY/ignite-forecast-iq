from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.data_preprocessing import MAX_UPLOAD_ROWS
from backend.main import app


def valid_row(day: int = 1) -> dict:
    return {
        "date": f"2026-01-{day:02d}",
        "channel": "Google Ads",
        "campaign_type": "Search",
        "campaign_name": f"Brand {day}",
        "spend": 100.0,
        "clicks": 40.0,
        "impressions": 1000.0,
        "conversions": 5.0,
        "revenue": 450.0,
        "roas": 4.5,
    }


class ApiSecurityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    def test_train_without_admin_token_returns_401(self) -> None:
        response = self.client.post("/api/train", json={"rows": [valid_row()], "modelPath": "pickle/model.pkl"})

        self.assertEqual(response.status_code, 401)

    def test_train_rejects_path_traversal_before_writing(self) -> None:
        with patch.dict(os.environ, {"TRAINING_ADMIN_TOKEN": "secret"}, clear=False):
            response = self.client.post(
                "/api/train",
                json={"rows": [valid_row()], "modelPath": "../../outside.pkl"},
                headers={"X-Training-Admin-Token": "secret"},
            )

        self.assertEqual(response.status_code, 400)
        self.assertIn("pickle", response.text)

    def test_oversized_payload_returns_clear_422(self) -> None:
        rows = [valid_row((index % 28) + 1) for index in range(MAX_UPLOAD_ROWS + 1)]
        response = self.client.post("/api/forecast", json={"rows": rows, "horizon": 30, "level": "overall"})

        self.assertEqual(response.status_code, 422)
        self.assertIn("maximum supported upload", response.text)


if __name__ == "__main__":
    unittest.main()
