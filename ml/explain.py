# C:\aimlmini\ml\explain.py
"""Compute feature contributions for the Insights page.

Uses the built in contribution output of the p50 XGBoost model (pred_contribs)
on a fixed sample of test rows. One hot columns produced by the pipeline are
added back together under their original feature names, so the ranking reads
as features a person can name, such as borough or call type, not individual
encoded columns. Results are merged into models/metrics.json.
"""
import json

import numpy as np
import pandas as pd
import xgboost as xgb
from joblib import load

MODEL = "models/p50.joblib"
TEST = "data/processed/test.csv"
SAMPLE = 5000
SEED = 42

CAT_COLS = ["hour_band", "borough", "zone", "incident_dispatch_area",
            "initial_call_type", "initial_severity_level_code"]
NUM_COLS = ["hour", "day_of_week", "month", "weekend"]
WEATHER_NUM = ["temperature_2m", "precipitation", "snowfall", "is_snow", "holiday"]
FEATURES = CAT_COLS + NUM_COLS + WEATHER_NUM
TARGET = "response_min"

PLAIN_NAMES = {
    "zone": "zip zone",
    "initial_call_type": "call type",
    "initial_severity_level_code": "severity",
    "borough": "borough",
    "hour": "hour of day",
    "hour_band": "hour band",
    "incident_dispatch_area": "dispatch area",
    "day_of_week": "day of week",
    "month": "month",
    "weekend": "weekend",
    "temperature_2m": "temperature",
    "precipitation": "precipitation",
    "snowfall": "snowfall",
    "is_snow": "snow",
    "holiday": "holiday",
}


def main() -> None:
    pipe = load(MODEL)
    test = pd.read_csv(TEST, dtype={c: str for c in CAT_COLS})
    for c in NUM_COLS:
        test[c] = pd.to_numeric(test[c]).astype(int)
    for c in WEATHER_NUM:
        test[c] = pd.to_numeric(test[c])
    test["initial_severity_level_code"] = test["initial_severity_level_code"].astype(str)
    sample = test.sample(SAMPLE, random_state=SEED)

    X = sample[FEATURES]
    X_trans = pipe.named_steps["prep"].transform(X)
    booster = pipe.named_steps["model"].get_booster()
    contribs = booster.predict(xgb.DMatrix(X_trans), pred_contribs=True)  # (rows, features + 1)
    contributions = contribs[:, :-1]  # last column is the base value

    names = pipe.named_steps["prep"].get_feature_names_out()
    # ColumnTransformer names look like "cat__borough_BRONX" or "num__hour".
    # Strip the transformer prefix, then remove the encoded value token so the
    # column is grouped under its original feature name.
    groups = []
    for n in names:
        rest = n.split("__", 1)[1]
        if n.startswith("cat__"):
            groups.append(rest.rsplit("_", 1)[0])
        else:
            groups.append(rest)

    df = pd.DataFrame(contributions, columns=groups)
    # One hot columns share an original feature name, so add them back together
    # before ranking, the same way model_service.explain_case does per request.
    df = df.T.groupby(level=0).sum().T
    global_rank = (
        df.abs().mean().sort_values(ascending=False)
    )
    top = [
        {"feature": feat, "plain_name": PLAIN_NAMES.get(feat, feat),
         "mean_abs_contribution_min": round(float(v), 3),
         "direction": "raises response time" if df[feat].mean() > 0 else "lowers response time"}
        for feat, v in global_rank.head(15).items()
    ]

    metrics = json.load(open("models/metrics.json"))
    metrics["shap_sample_rows"] = SAMPLE
    metrics["shap_top_features"] = top
    metrics["top_drivers_plain"] = [
        f"{t['plain_name']} ({t['direction']})" for t in top[:5]
    ]
    json.dump(metrics, open("models/metrics.json", "w"), indent=2)
    print(json.dumps(metrics["top_drivers_plain"], indent=2))


if __name__ == "__main__":
    main()
