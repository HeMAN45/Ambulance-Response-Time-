# C:\aimlmini\app\services\stats_service.py
"""Reads the precomputed statistics files and exposes lookup functions.

Every JSON file here was produced by the ml pipeline. Nothing calculates from
raw data during a request; these functions only filter and reshape saved rows.
"""
import json
import os

from flask import current_app

_state: dict = {}

FILES = [
    "zip_stats.json", "hourly_stats.json", "heatmap_stats.json",
    "trend_stats.json", "breakdown_stats.json", "distribution_stats.json",
    "clean_report.json", "split_report.json", "weather_stats.json",
]

MIN_ZONE_INCIDENTS = 30

# The stats file stores the three heatmaps as h1, h2 and h3. The API names them
# by meaning, so map the request name to the stored key.
HEATMAP_KEYS = {
    "hour_weekday": "h1",
    "borough_hour": "h2",
    "severity_band": "h3",
}


def init(processed_dir: str) -> None:
    for f in FILES:
        path = os.path.join(processed_dir, f)
        _state[f] = json.load(open(path)) if os.path.exists(path) else None


def _ensure_loaded() -> None:
    if not _state.get("zip_stats.json"):
        init(current_app.config["PROCESSED_DIR"])


def _file(name: str):
    _ensure_loaded()
    return _state[name]


def get_zones(hour_band: str, severity: str) -> list[dict]:
    """Zone rows for one hour_band and severity combination. Sparse zones are
    flagged rather than dropped, so the map can show them as not enough data."""
    _ensure_loaded()
    recs = _state["zip_stats.json"]["records"]
    return [r for r in recs if r["hour_band"] == hour_band and r["severity"] == severity]


def get_summary(hour_band: str, severity: str) -> dict | None:
    _ensure_loaded()
    return _state["zip_stats.json"]["summary"].get(f"{hour_band}|{severity}")


def get_zone_hourly(zone: str) -> list[dict]:
    _ensure_loaded()
    return _state["zip_stats.json"]["zone_hourly"].get(zone, [])


def get_hourly(borough: str) -> list[dict]:
    _ensure_loaded()
    recs = _state["hourly_stats.json"]["records"]
    return [r for r in recs if r["borough"] == borough]


def get_heatmap(kind: str) -> list[dict]:
    _ensure_loaded()
    return _state["heatmap_stats.json"].get(HEATMAP_KEYS.get(kind, kind), [])


def get_trend(borough: str) -> list[dict]:
    _ensure_loaded()
    recs = _state["trend_stats.json"]["records"]
    return [r for r in recs if r["borough"] == borough]


def get_zone_trend() -> list[dict]:
    _ensure_loaded()
    return _state["trend_stats.json"]["zone_trend"]


def get_breakdown(kind: str) -> list[dict]:
    _ensure_loaded()
    return _state["breakdown_stats.json"].get(kind, [])


def get_distribution(borough: str) -> dict | None:
    _ensure_loaded()
    return _state["distribution_stats.json"].get(borough)


def get_weather_effect() -> dict | None:
    _ensure_loaded()
    return _state["weather_stats.json"]


def get_geo_stats() -> dict:
    """Summary numbers used by the Method page and the model card."""
    _ensure_loaded()
    return {
        "clean_report": _state["clean_report.json"],
        "split_report": _state["split_report.json"],
    }


def build_model_card() -> dict:
    _ensure_loaded()
    from app.services import model_service
    metrics = model_service.metrics()
    clean = _state["clean_report.json"] or {}
    split = _state["split_report.json"] or {}
    worst_borough = max(metrics.get("error_by_borough", {}).items(), key=lambda kv: kv[1], default=None)
    return {
        "task": "Predict ambulance response time in minutes for a zone, hour, day and severity, with a 10th to 90th percentile range.",
        "data_source": "NYC EMS Incident Dispatch Data, FDNY, NYC Open Data, dataset 76xm-jjuj, calendar year 2023",
        "training_period": split.get("train_period"),
        "test_period": split.get("test_period"),
        "row_counts": {
            "sampled_rows": clean.get("source_rows"),
            "after_valid_flag": clean.get("after_valid_flag"),
            "after_60min_cut": clean.get("after_60min_cut"),
            "train_rows": split.get("train_rows"),
            "test_rows": split.get("test_rows"),
        },
        "filters": {
            "valid response flag": f"removed {clean.get('removed_invalid_flag')} rows",
            "null target": f"removed {clean.get('removed_null_target')} rows",
            "above 60 minutes": f"removed {clean.get('removed_over_60min')} rows",
            "sampling": clean.get("sampling"),
        },
        "features": split.get("features"),
        "leakage_rules": [
            "No dispatch, travel or assignment timestamps are used. They are recorded after the call.",
            "Only initial call type and initial severity are used, never the final versions.",
            "All aggregates were computed from the training period only.",
        ],
        "models": [{k: v for k, v in m.items() if not k.startswith("_")} for m in metrics.get("models", [])],
        "best_model": metrics.get("best_model"),
        "beats_baseline": metrics.get("beats_baseline"),
        "range_coverage": metrics.get("range_coverage"),
        "weather": metrics.get("weather_experiment"),
        "known_weaknesses": [
            f"Highest mean absolute error is for {worst_borough[0]} at {worst_borough[1]} minutes." if worst_borough else "Error slices not available.",
            "Zones with few incidents have wide uncertainty and are hidden on the map below 30 incidents.",
            "Exact incident locations are not published, so place is only known at zip zone level.",
            "The model estimates a distribution level response time, not the outcome of any single dispatch.",
        ],
        "intended_use": "Planning and analysis. It shows typical response times and what drives them. It is not for live dispatch decisions and makes no clinical or operational claims.",
        "limitations": [
            "One citywide model. Weather is a single citywide series, not local conditions at the incident.",
            "Predictions assume a dry non holiday day at the 2023 average temperature for the current month, because the form does not collect weather.",
            "Sampling keeps every 4th day of the month, which preserves seasonal patterns but not every calendar day.",
            "Predictions assume the current month for the month feature.",
        ],
    }
