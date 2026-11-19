# C:\aimlmini\ml\weather.py
"""Download New York City hourly weather for 2023 and precompute effect slices.

The incident data has no coordinates, so one citywide hourly series is used.
The CSV it writes is merged into the feature tables by features.py, and the
with and without comparison lives in weather_experiment.py.
"""
import json
import os

import holidays as holiday_lib
import pandas as pd
import requests

WEATHER_CSV = "data/processed/weather_2023.csv"
WEATHER_STATS = "data/processed/weather_stats.json"
WEATHER_MONTHLY = "data/processed/weather_monthly.json"
CLEAN = "data/processed/clean.csv"
TARGET = "response_min"

URL = "https://archive-api.open-meteo.com/v1/archive"
PARAMS = {
    "latitude": 40.7128,
    "longitude": -74.0060,
    "start_date": "2023-01-01",
    "end_date": "2023-12-31",
    "hourly": "temperature_2m,precipitation,snowfall",
    "timezone": "America/New_York",
}


def fetch_weather() -> pd.DataFrame:
    """Download the hourly series once and cache it under data/processed."""
    if os.path.exists(WEATHER_CSV):
        return pd.read_csv(WEATHER_CSV, parse_dates=["weather_hour"])

    resp = requests.get(URL, params=PARAMS, timeout=120)
    resp.raise_for_status()
    hourly = resp.json()["hourly"]
    df = pd.DataFrame({
        "weather_hour": pd.to_datetime(hourly["time"]),
        "temperature_2m": hourly["temperature_2m"],
        "precipitation": hourly["precipitation"],
        "snowfall": hourly["snowfall"],
    })
    df["is_snow"] = (df["snowfall"] > 0).astype(int)
    us = holiday_lib.US(years=2023)
    df["date"] = df["weather_hour"].dt.date
    df["holiday"] = df["date"].map(lambda d: int(d in us))
    df["holiday_name"] = df["date"].map(lambda d: us.get(d, ""))
    os.makedirs("data/processed", exist_ok=True)
    df.to_csv(WEATHER_CSV, index=False)
    return df


def slice_stats(g: pd.DataFrame) -> dict:
    return {
        "count": int(len(g)),
        "median": round(float(g[TARGET].median()), 2),
        "p90": round(float(g[TARGET].quantile(0.9)), 2),
        "share_over_10": round(float((g[TARGET] > 10).mean()), 4),
    }


def precipitation_band(mm: float) -> str:
    if mm <= 0:
        return "dry"
    if mm < 0.5:
        return "light rain"
    if mm < 2.0:
        return "moderate rain"
    return "heavy rain"


def build_effect_stats(weather: pd.DataFrame) -> dict:
    df = pd.read_csv(CLEAN)
    df["weather_hour"] = pd.to_datetime(df["incident_datetime"]).dt.floor("h")
    df = df.merge(weather, on="weather_hour", how="left")
    df["precipitation"] = df["precipitation"].fillna(0.0)
    df["snowfall"] = df["snowfall"].fillna(0.0)
    df["holiday"] = df["holiday"].fillna(0).astype(int)
    df["precipitation_band"] = df["precipitation"].map(precipitation_band)
    df["snow"] = (df["snowfall"] > 0).astype(int)

    bands = [
        {"precipitation_band": band, "holiday": int(hol), **slice_stats(g)}
        for (band, hol), g in df.groupby(["precipitation_band", "holiday"])
    ]
    snow = [{"snow": int(flag), **slice_stats(g)} for flag, g in df.groupby("snow")]
    return {
        "precipitation": bands,
        "snow": snow,
        "source": "Open Meteo archive API, one citywide hourly series for New York City, 2023",
        "holiday_source": "holidays package, US calendar, 2023",
    }


def main() -> None:
    weather = fetch_weather()
    stats = build_effect_stats(weather)
    json.dump(stats, open(WEATHER_STATS, "w"), indent=2)
    monthly = (
        weather.assign(month=weather["weather_hour"].dt.month)
        .groupby("month")["temperature_2m"].mean().round(2)
    )
    json.dump({str(m): float(v) for m, v in monthly.items()}, open(WEATHER_MONTHLY, "w"), indent=2)
    print(f"weather rows: {len(weather)}")
    print(f"precipitation slices: {len(stats['precipitation'])}")
    print("weather_stats written")


if __name__ == "__main__":
    main()
