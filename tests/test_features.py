import pandas as pd

from backend.data_preprocessing import add_holiday_features, feature_frame


def test_black_friday_week_flagged():
    df = pd.DataFrame({"date": ["2025-11-28"], "spend": [1000], "revenue": [5000]})
    result = add_holiday_features(df)
    assert result["is_holiday_week"].iloc[0] == 1


def test_regular_tuesday_not_flagged():
    df = pd.DataFrame({"date": ["2025-03-11"], "spend": [1000], "revenue": [5000]})
    result = add_holiday_features(df)
    assert result["is_holiday_week"].iloc[0] == 0


def test_feature_frame_includes_seasonality_columns():
    dates = pd.date_range("2025-01-01", periods=45, freq="D")
    df = pd.DataFrame(
        {
            "date": dates.strftime("%Y-%m-%d"),
            "spend": 1000,
            "clicks": 500,
            "impressions": 10000,
            "conversions": 50,
            "revenue": 5000,
            "roas": 5,
        }
    )
    X, y = feature_frame(df, "revenue")
    assert "is_holiday_week" in X.columns
    assert "days_to_black_friday" in X.columns
    assert len(y) == len(X)
