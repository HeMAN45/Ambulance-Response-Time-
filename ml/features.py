# C:\aimlmini\ml\features.py
"""Build model features and split by time.

Time features come only from incident_datetime, which is known at call time.
The split sorts by time and takes the oldest 80 percent for training and the
newest 20 percent for testing. A random split would leak the future into the
past, because zone and hour aggregates would see test period rows.
"""
import json
import os

import numpy as np
import pandas as pd

IN_CSV = "data/processed/clean.csv"
WEATHER_CSV = "data/processed/weather_2023.csv"
TRAIN_CSV = "data/processed/train.csv"
TEST_CSV = "data/processed/test.csv"
SPLIT_REPORT = "data/processed/split_report.json"

HOUR_BANDS = [
    ("overnight", 0, 5),
    ("morning", 6, 11),
    ("midday", 12, 17),
    ("evening", 18, 23),
]

WEATHER_FEATURES = ["temperature_2m", "precipitation", "snowfall", "is_snow", "holiday"]

FEATURES = [
    "hour", "day_of_week", "month", "weekend", "hour_band",
    "borough", "zone", "incident_dispatch_area",
    "initial_call_type", "initial_severity_level_code",
] + WEATHER_FEATURES

TARGET = "response_min"


def attach_weather(df: pd.DataFrame) -> pd.DataFrame:
    """Join the citywide hourly weather and holiday series to each incident."""
    if not os.path.exists(WEATHER_CSV):
        raise SystemExit("weather_2023.csv is missing, run ml/weather.py first")
    weather = pd.read_csv(
        WEATHER_CSV, parse_dates=["weather_hour"],
        usecols=["weather_hour", "temperature_2m", "precipitation", "snowfall", "is_snow", "holiday"],
    )
    out = df.copy()
    out["weather_hour"] = pd.to_datetime(out["incident_datetime"]).dt.floor("h")
    out = out.merge(weather, on="weather_hour", how="left")
    out["precipitation"] = out["precipitation"].fillna(0.0)
    out["snowfall"] = out["snowfall"].fillna(0.0)
    out["is_snow"] = out["is_snow"].fillna(0).astype(int)
    out["holiday"] = out["holiday"].fillna(0).astype(int)
    out["temperature_2m"] = out["temperature_2m"].interpolate().ffill().bfill()
    return out


def add_features(df: pd.DataFrame) -> pd.DataFrame:
    dt = pd.to_datetime(df["incident_datetime"])
    out = df.copy()
    out["hour"] = dt.dt.hour.astype(int)
    out["day_of_week"] = dt.dt.day_of_week.astype(int)  # Monday is 0
    out["month"] = dt.dt.month.astype(int)
    out["weekend"] = (out["day_of_week"] >= 5).astype(int)
    band = np.select(
        [out["hour"].between(lo, hi) for _, lo, hi in HOUR_BANDS],
        [name for name, _, _ in HOUR_BANDS],
        default="overnight",
    )
    out["hour_band"] = band
    out = attach_weather(out)
    return out[FEATURES + [TARGET] + ["incident_datetime"]]


def main() -> None:
    df = pd.read_csv(IN_CSV)
    df = add_features(df)

    train_size = int(len(df) * 0.8)
    train = df.iloc[:train_size]  # file is already sorted by time
    test = df.iloc[train_size:]

    train.to_csv(TRAIN_CSV, index=False)
    test.to_csv(TEST_CSV, index=False)

    report = {
        "total_rows": len(df),
        "train_rows": len(train),
        "test_rows": len(test),
        "train_period": [str(train["incident_datetime"].min()), str(train["incident_datetime"].max())],
        "test_period": [str(test["incident_datetime"].min()), str(test["incident_datetime"].max())],
        "split": "sorted by time, oldest 80 percent train, newest 20 percent test",
        "features": FEATURES,
    }
    json.dump(report, open(SPLIT_REPORT, "w"), indent=2)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
