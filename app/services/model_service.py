# C:\aimlmini\app\services\model_service.py
"""Loads the trained pipelines and artifacts once and exposes small functions.

Flask never trains anything here. The three quantile pipelines, the schema and
the lookup files are read once at startup, and every request only transforms a
single row through the fitted pipelines.
"""
import datetime
import json
import os

import numpy as np
import pandas as pd
import xgboost as xgb
from joblib import load

from flask import current_app

CAT_COLS = ["hour_band", "borough", "zone", "incident_dispatch_area",
            "initial_call_type", "initial_severity_level_code"]
NUM_COLS = ["hour", "day_of_week", "month", "weekend"]
WEATHER_NUM = ["temperature_2m", "precipitation", "snowfall", "is_snow", "holiday"]
FEATURES = CAT_COLS + NUM_COLS + WEATHER_NUM
HOUR_BANDS = [("overnight", 0, 5), ("morning", 6, 11), ("midday", 12, 17), ("evening", 18, 23)]

PLAIN_NAMES = {
    "zone": "zip zone", "initial_call_type": "call type",
    "initial_severity_level_code": "severity", "borough": "borough",
    "hour": "hour of day", "hour_band": "hour band",
    "incident_dispatch_area": "dispatch area", "day_of_week": "day of week",
    "month": "month", "weekend": "weekend",
    "temperature_2m": "temperature", "precipitation": "precipitation",
    "snowfall": "snowfall", "is_snow": "snow", "holiday": "holiday",
}

_state: dict = {}


def init(model_dir: str, processed_dir: str) -> None:
    """Read all artifacts. Called once from create_app."""
    _state["pipelines"] = {
        q: load(os.path.join(model_dir, f"{q}.joblib")) for q in ("p10", "p50", "p90")
    }
    _state["schema"] = json.load(open(os.path.join(model_dir, "schema.json")))
    _state["metrics"] = json.load(open(os.path.join(model_dir, "metrics.json")))
    _state["calibration"] = json.load(open(os.path.join(model_dir, "calibration.json")))
    _state["crosswalk"] = json.load(open(os.path.join(processed_dir, "zip_crosswalk.json")))

    # Monthly mean temperature from the 2023 weather series, used as the default
    # when the form does not collect weather. This is precomputed by ml/weather.py
    # so startup does not read the full hourly CSV.
    monthly_path = os.path.join(processed_dir, "weather_monthly.json")
    if os.path.exists(monthly_path):
        with open(monthly_path) as f:
            _state["weather_monthly"] = {int(k): float(v) for k, v in json.load(f).items()}
    else:
        _state["weather_monthly"] = {}


def _ensure_loaded() -> None:
    if not _state.get("pipelines"):
        init(current_app.config["MODEL_DIR"], current_app.config["PROCESSED_DIR"])


def schema() -> dict:
    _ensure_loaded()
    return _state["schema"]


def crosswalk() -> dict:
    _ensure_loaded()
    return _state["crosswalk"]


def metrics() -> dict:
    _ensure_loaded()
    return _state["metrics"]


def calibration() -> dict:
    _ensure_loaded()
    return _state["calibration"]


def hour_band_for(hour: int) -> str:
    for name, lo, hi in HOUR_BANDS:
        if lo <= hour <= hi:
            return name
    return "overnight"


def build_features(data: dict) -> pd.DataFrame:
    """Turn validated request input into the one row the pipelines expect.

    month is taken from the request date, because the form does not ask for it
    and the model was trained with month as a seasonality feature. weekend is
    derived from day_of_week. dispatch area comes from the training period's
    most common area for the zone. Weather is not collected by the form, so the
    estimate assumes a dry non holiday day at the 2023 mean temperature for the
    current month.
    """
    zone = _state["crosswalk"]["zip_to_zone"][str(data["zipcode"])]
    month = datetime.date.today().month
    row = {
        "hour": int(data["hour"]),
        "day_of_week": int(data["day_of_week"]),
        "month": month,
        "weekend": 1 if int(data["day_of_week"]) >= 5 else 0,
        "hour_band": hour_band_for(int(data["hour"])),
        "borough": data["borough"],
        "zone": zone,
        "incident_dispatch_area": _state["crosswalk"]["zone_to_area"].get(zone, "Unknown"),
        "initial_call_type": data["call_type"],
        "initial_severity_level_code": data["severity"],
        "temperature_2m": float(_state.get("weather_monthly", {}).get(month, 0.0)),
        "precipitation": 0.0,
        "snowfall": 0.0,
        "is_snow": 0,
        "holiday": 0,
    }
    return pd.DataFrame([row], columns=FEATURES), zone


def predict_case(data: dict) -> dict:
    _ensure_loaded()
    X, zone = build_features(data)
    out = {}
    for q in ("p10", "p50", "p90"):
        pred = float(_state["pipelines"][q].predict(X)[0])
        out[q] = round(max(pred, 0.0), 1)
    out["model_version"] = _state["schema"]["model_version"]
    out["zone"] = zone
    return out


def explain_case(data: dict) -> dict:
    _ensure_loaded()
    X, zone = build_features(data)
    pipe = _state["pipelines"]["p50"]
    X_trans = pipe.named_steps["prep"].transform(X)
    booster = pipe.named_steps["model"].get_booster()
    contribs = booster.predict(xgb.DMatrix(X_trans), pred_contribs=True)
    base = float(contribs[0, -1])

    names = pipe.named_steps["prep"].get_feature_names_out()
    rows = []
    for i, n in enumerate(names):
        rest = n.split("__", 1)[1]
        feature = rest.rsplit("_", 1)[0] if n.startswith("cat__") else rest
        rows.append({
            "feature": feature,
            "plain_name": PLAIN_NAMES.get(feature, feature),
            "contribution": round(float(contribs[0, i]), 2),
        })

    # add one hot columns back together under their original feature names
    grouped: dict[str, float] = {}
    for r in rows:
        grouped[r["feature"]] = grouped.get(r["feature"], 0.0) + r["contribution"]
    contributions = sorted(
        [{"feature": f, "plain_name": PLAIN_NAMES.get(f, f), "contribution": round(v, 2)}
         for f, v in grouped.items()],
        key=lambda d: -abs(d["contribution"]),
    )
    p50 = float(_state["pipelines"]["p50"].predict(X)[0])
    return {"base_value": round(base, 2), "p50": round(max(p50, 0.0), 1),
            "contributions": contributions, "zone": zone}
