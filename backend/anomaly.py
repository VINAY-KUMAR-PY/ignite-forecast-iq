"""Statistical anomaly detection for campaign performance data."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import List

import numpy as np
import pandas as pd


@dataclass
class Anomaly:
    date: str
    channel: str
    metric: str
    actual: float
    expected: float
    z_score: float
    severity: str
    description: str

    def to_dict(self) -> dict:
        return asdict(self)


def _daily_channel_frame(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(columns=["date", "channel", "revenue", "spend", "clicks", "impressions", "roas", "ctr"])
    daily = (
        frame.groupby(["date", "channel"], as_index=False)[["revenue", "spend", "clicks", "impressions"]]
        .sum()
        .sort_values(["channel", "date"])
        .reset_index(drop=True)
    )
    daily["roas"] = np.where(daily["spend"] > 0, daily["revenue"] / daily["spend"], 0.0)
    daily["ctr"] = np.where(daily["impressions"] > 0, daily["clicks"] / daily["impressions"], 0.0)
    return daily.replace([np.inf, -np.inf], 0).fillna(0)


def detect_anomalies(frame: pd.DataFrame, z_threshold: float = 2.5) -> List[Anomaly]:
    """
    Detect statistical anomalies using rolling z-score.

    For each channel and metric, compare each day to the prior 28-day rolling
    mean/std. Also flags 3-day ROAS declines greater than 20%.
    """
    daily = _daily_channel_frame(frame)
    anomalies: list[Anomaly] = []
    if daily.empty:
        return anomalies

    for channel, channel_frame in daily.groupby("channel"):
        channel_frame = channel_frame.sort_values("date").reset_index(drop=True)
        for metric in ["revenue", "spend", "roas", "ctr"]:
            values = pd.to_numeric(channel_frame[metric], errors="coerce").fillna(0)
            expected = values.shift(1).rolling(28, min_periods=7).mean()
            std = values.shift(1).rolling(28, min_periods=7).std(ddof=1).replace(0, np.nan)
            z_scores = ((values - expected) / std).replace([np.inf, -np.inf], np.nan)
            for idx, z_score in z_scores.dropna().items():
                if abs(float(z_score)) <= z_threshold:
                    continue
                actual = float(values.iloc[idx])
                exp = float(expected.iloc[idx])
                severity = "critical" if abs(float(z_score)) > 3.5 else "warning"
                direction = "above" if actual >= exp else "below"
                anomalies.append(
                    Anomaly(
                        date=str(channel_frame.at[idx, "date"]),
                        channel=str(channel),
                        metric=metric,
                        actual=round(actual, 4),
                        expected=round(exp, 4),
                        z_score=round(float(z_score), 2),
                        severity=severity,
                        description=f"{metric.upper()} on {channel} was {direction} its 28-day expected level.",
                    )
                )

        roas = pd.to_numeric(channel_frame["roas"], errors="coerce").fillna(0)
        decline = roas.pct_change(periods=3).replace([np.inf, -np.inf], np.nan)
        for idx, pct in decline.dropna().items():
            if float(pct) >= -0.20:
                continue
            anomalies.append(
                Anomaly(
                    date=str(channel_frame.at[idx, "date"]),
                    channel=str(channel),
                    metric="roas",
                    actual=round(float(roas.iloc[idx]), 4),
                    expected=round(float(roas.iloc[max(0, idx - 3)]), 4),
                    z_score=round(float(pct * 10), 2),
                    severity="critical" if pct <= -0.35 else "warning",
                    description=f"ROAS on {channel} declined {abs(float(pct)) * 100:.1f}% over three days.",
                )
            )

    anomalies.sort(key=lambda item: item.date, reverse=True)
    return anomalies


def compute_trend_breaks(frame: pd.DataFrame) -> List[dict]:
    """Detect simple CUSUM revenue trend breaks by channel."""
    daily = _daily_channel_frame(frame)
    breaks: list[dict] = []
    if daily.empty:
        return breaks

    for channel, channel_frame in daily.groupby("channel"):
        revenue = pd.to_numeric(channel_frame.sort_values("date")["revenue"], errors="coerce").fillna(0).to_numpy()
        if len(revenue) < 21:
            continue
        mean = float(np.mean(revenue))
        std = float(np.std(revenue, ddof=1)) or 1.0
        pos = neg = 0.0
        threshold = 5 * std
        for idx, value in enumerate(revenue):
            centered = float(value) - mean
            pos = max(0.0, pos + centered - 0.5 * std)
            neg = min(0.0, neg + centered + 0.5 * std)
            if pos > threshold or abs(neg) > threshold:
                previous = float(np.mean(revenue[max(0, idx - 14) : max(1, idx - 1)])) or 1.0
                current = float(np.mean(revenue[idx : min(len(revenue), idx + 7)]))
                magnitude = ((current - previous) / previous) * 100 if previous else 0.0
                breaks.append(
                    {
                        "date": str(channel_frame.iloc[idx]["date"]),
                        "channel": str(channel),
                        "direction": "up" if magnitude >= 0 else "down",
                        "magnitude_pct": round(float(magnitude), 2),
                    }
                )
                pos = neg = 0.0

    breaks.sort(key=lambda item: item["date"], reverse=True)
    return breaks
