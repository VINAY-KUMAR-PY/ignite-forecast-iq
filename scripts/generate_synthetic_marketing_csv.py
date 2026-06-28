"""Generate deterministic large marketing CSV fixtures for evaluator stress tests."""
from __future__ import annotations

import argparse
import csv
from datetime import date, timedelta
from pathlib import Path


CHANNELS = [
    ("Google Ads", "Search", "Brand Search", 4.8, 115.0),
    ("Google Ads", "Shopping", "Shopping Best Sellers", 4.1, 95.0),
    ("Meta Ads", "Prospecting", "Lookalike Prospecting", 2.7, 90.0),
    ("Meta Ads", "Retargeting", "Cart Retargeting", 3.3, 75.0),
    ("Microsoft Ads", "Search", "Bing Brand", 4.3, 48.0),
    ("Microsoft Ads", "Shopping", "Bing Shopping", 3.8, 42.0),
]


def write_fixture(path: Path, rows: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    start = date(2024, 1, 1)
    fieldnames = [
        "date",
        "channel",
        "campaign_type",
        "campaign_name",
        "spend",
        "clicks",
        "impressions",
        "conversions",
        "revenue",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for index in range(rows):
            day = index // len(CHANNELS)
            channel, campaign_type, campaign_name, roas, base_spend = CHANNELS[index % len(CHANNELS)]
            current = start + timedelta(days=day)
            weekly = 1 + ((day % 7) - 3) * 0.015
            trend = 1 + min(day, 720) / 5000
            spend = round(base_spend * weekly * trend * (1 + (index % 11) * 0.006), 2)
            revenue = round(spend * roas * (1 + ((day + index) % 13) * 0.004), 2)
            clicks = int(spend * (1.8 + (index % 5) * 0.15))
            impressions = clicks * (35 + (index % 17))
            conversions = round(max(1.0, clicks * (0.035 + (index % 3) * 0.004)), 2)
            writer.writerow(
                {
                    "date": current.isoformat(),
                    "channel": channel,
                    "campaign_type": campaign_type,
                    "campaign_name": campaign_name,
                    "spend": spend,
                    "clicks": clicks,
                    "impressions": impressions,
                    "conversions": conversions,
                    "revenue": revenue,
                }
            )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--rows", default=50_400, type=int)
    args = parser.parse_args()
    write_fixture(args.output, args.rows)
    print(f"Wrote {args.rows} synthetic rows to {args.output}")


if __name__ == "__main__":
    main()
