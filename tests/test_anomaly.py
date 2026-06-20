import pandas as pd

from backend.anomaly import compute_trend_breaks, detect_anomalies


def make_frame_with_spike():
    rows = []
    for day in range(45):
        revenue = 5000
        spend = 1000
        if day == 30:
            revenue = 15000
        rows.append(
            {
                "date": (pd.Timestamp("2025-01-01") + pd.Timedelta(days=day)).strftime("%Y-%m-%d"),
                "channel": "Google Ads",
                "campaign_type": "Search",
                "campaign_name": "Brand",
                "spend": spend,
                "clicks": 500,
                "impressions": 10000,
                "conversions": 50,
                "revenue": revenue,
                "roas": revenue / spend,
            }
        )
    return pd.DataFrame(rows)


def test_anomaly_detected_on_spike():
    frame = make_frame_with_spike()
    anomalies = detect_anomalies(frame, z_threshold=2.0)
    assert len(anomalies) >= 1
    assert any(a.metric == "roas" for a in anomalies)


def test_no_false_positives_on_stable_data():
    frame = make_frame_with_spike()
    frame["revenue"] = 5000
    frame["roas"] = 5
    anomalies = detect_anomalies(frame, z_threshold=2.5)
    assert anomalies == []


def test_trend_break_detected():
    frame = make_frame_with_spike()
    frame.loc[25:, "revenue"] = 9000
    frame["roas"] = frame["revenue"] / frame["spend"]
    breaks = compute_trend_breaks(frame)
    assert any(item["channel"] == "Google Ads" for item in breaks)
