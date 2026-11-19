# C:\aimlmini\ml\train.py
"""Train the baseline, Ridge, Random Forest, XGBoost and three quantile models.

Split rule: train.py never shuffles. train.csv holds the oldest 80 percent of
incidents and test.csv the newest 20 percent, built by features.py. Every model
is a scikit learn Pipeline so the web app applies exactly the same encoding at
prediction time as at training time.

Saved artifacts:
models/p10.joblib, p50.joblib, p90.joblib  quantile pipelines used by the app
models/schema.json                         allowed input values for the app
models/metrics.json                        model comparison and test metrics
models/calibration.json                    calibration data for the Method page
"""
import json
import os
import time

# Cap BLAS threads before numpy and xgboost load. This keeps training within the
# memory of a small laptop, and single row inference does not need more threads.
for _name in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ.setdefault(_name, "1")

import numpy as np
import pandas as pd
import xgboost as xgb
from joblib import dump
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

TRAIN = "data/processed/train.csv"
TEST = "data/processed/test.csv"
SEED = 42

CAT_COLS = ["hour_band", "borough", "zone", "incident_dispatch_area",
            "initial_call_type", "initial_severity_level_code"]
NUM_COLS = ["hour", "day_of_week", "month", "weekend"]
WEATHER_NUM = ["temperature_2m", "precipitation", "snowfall", "is_snow", "holiday"]
FEATURES = CAT_COLS + NUM_COLS + WEATHER_NUM
TARGET = "response_min"


def load() -> tuple[pd.DataFrame, pd.DataFrame]:
    train = pd.read_csv(TRAIN, dtype={c: str for c in CAT_COLS})
    test = pd.read_csv(TEST, dtype={c: str for c in CAT_COLS})
    for d in (train, test):
        for c in NUM_COLS:
            d[c] = pd.to_numeric(d[c]).astype(int)
        for c in WEATHER_NUM:
            d[c] = pd.to_numeric(d[c])
        d["initial_severity_level_code"] = d["initial_severity_level_code"].astype(str)
    return train, test


def preprocessor() -> ColumnTransformer:
    return ColumnTransformer(
        [("cat", OneHotEncoder(handle_unknown="ignore"), CAT_COLS),
         ("num", "passthrough", NUM_COLS + WEATHER_NUM)],
        remainder="drop",
    )


def evaluate(name: str, model, test: pd.DataFrame) -> dict:
    pred = model.predict(test[FEATURES])
    mae = mean_absolute_error(test[TARGET], pred)
    rmse = float(np.sqrt(mean_squared_error(test[TARGET], pred)))
    r2 = float(r2_score(test[TARGET], pred))
    within2 = float((np.abs(pred - test[TARGET]) <= 2).mean())
    return {"name": name, "mae": round(mae, 3), "rmse": round(rmse, 3),
            "r2": round(r2, 3), "within_2min_share": round(within2, 4), "_pred": pred}


class BoroughHourBaseline:
    """Median response time by borough and hour, from training data only."""

    def __init__(self, table: pd.DataFrame, global_median: float):
        self.table = table
        self.global_median = global_median

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        keys = list(zip(X["borough"], X["hour"]))
        return np.array([
            self.table.get(k, self.global_median) for k in keys
        ], dtype=float)


def main() -> None:
    train, test = load()
    y_tr, y_te = train[TARGET], test[TARGET]
    metrics = {"models": [], "trained_at": time.strftime("%Y-%m-%d %H:%M:%S")}

    # ---- baseline ----
    table = train.groupby(["borough", "hour"])[TARGET].median().to_dict()
    baseline = BoroughHourBaseline(table, float(y_tr.median()))
    m = evaluate("Baseline: median by borough and hour", baseline, test)
    m.pop("_pred")
    metrics["models"].append(m)
    metrics["baseline_mae"] = m["mae"]
    print(m)

    # ---- ridge ----
    ridge = Pipeline([("prep", preprocessor()),
                      ("model", Ridge(alpha=1.0))])
    ridge.fit(train[FEATURES], y_tr)
    m = evaluate("Ridge regression", ridge, test)
    m.pop("_pred")
    metrics["models"].append(m)
    print(m)

    # ---- random forest ----
    rf = Pipeline([("prep", preprocessor()),
                   ("model", RandomForestRegressor(
                       n_estimators=100, max_depth=20, min_samples_leaf=20,
                       n_jobs=2, random_state=SEED))])
    rf.fit(train[FEATURES], y_tr)
    m = evaluate("Random Forest", rf, test)
    m.pop("_pred")
    metrics["models"].append(m)
    print(m)

    # ---- xgboost, the final point model ----
    xgbr = Pipeline([("prep", preprocessor()),
                     ("model", xgb.XGBRegressor(
                         n_estimators=400, learning_rate=0.08, max_depth=8,
                         subsample=0.9, colsample_bytree=0.9,
                             tree_method="hist", random_state=SEED, n_jobs=2))])
    xgbr.fit(train[FEATURES], y_tr)
    m = evaluate("XGBoost", xgbr, test)
    m.pop("_pred")
    metrics["models"].append(m)
    print(m)

    # ---- three quantile models, saved for the app ----
    quantile_preds = {}
    for alpha, name, fname in [(0.1, "p10", "p10"), (0.5, "p50", "p50"), (0.9, "p90", "p90")]:
        pipe = Pipeline([("prep", preprocessor()),
                         ("model", xgb.XGBRegressor(
                             objective="reg:quantileerror", quantile_alpha=alpha,
                             n_estimators=400, learning_rate=0.08, max_depth=8,
                             subsample=0.9, colsample_bytree=0.9,
                         tree_method="hist", random_state=SEED, n_jobs=2))])
        pipe.fit(train[FEATURES], y_tr)
        dump(pipe, f"models/{fname}.joblib")
        pred = pipe.predict(test[FEATURES])
        quantile_preds[name] = pred
        mae = mean_absolute_error(y_te, pred)
        print(f"{name}: MAE {mae:.3f}")
        metrics["quantile_models"] = metrics.get("quantile_models", []) + [
            {"name": name, "alpha": alpha, "mae": round(float(mae), 3)}]

    # ---- range coverage ----
    covered = ((quantile_preds["p10"] <= y_te) & (y_te <= quantile_preds["p90"]))
    metrics["range_coverage"] = round(float(covered.mean()), 4)
    coverage_by_borough = {
        b: round(float(g["covered"].mean()), 4)
        for b, g in pd.DataFrame({"borough": test["borough"], "covered": covered}).groupby("borough")
    }
    print("range coverage:", metrics["range_coverage"])

    # ---- error slices for the Method page and model card ----
    p50 = quantile_preds["p50"]
    abs_err = np.abs(p50 - y_te)
    metrics["error_by_borough"] = {b: round(float(e), 2) for b, e in
                                   pd.Series(abs_err).groupby(test["borough"].values).mean().items()}
    metrics["error_by_hour"] = {int(h): round(float(e), 2) for h, e in
                                pd.Series(abs_err).groupby(test["hour"].values).mean().items()}
    metrics["error_by_severity"] = {s: round(float(e), 2) for s, e in
                                    pd.Series(abs_err).groupby(test["initial_severity_level_code"].values).mean().items()}

    # ---- feature importance from the p50 model ----
    model = xgbr.named_steps["model"]
    importances = model.feature_importances_
    names = xgbr.named_steps["prep"].get_feature_names_out()
    feat_imp = sorted(
        [{"feature": n.split("__", 1)[1], "importance": round(float(i), 5)}
         for n, i in zip(names, importances)],
        key=lambda d: -d["importance"],
    )
    metrics["feature_importance"] = feat_imp[:20]

    # ---- calibration ----
    bins = np.quantile(p50, np.linspace(0, 1, 11))
    bin_ids = np.clip(np.digitize(p50, bins[1:-1]), 0, 9)
    calib = []
    for b in range(10):
        mask = bin_ids == b
        calib.append({
            "bin": b,
            "predicted": round(float(p50[mask].mean()), 2),
            "actual": round(float(y_te[mask].mean()), 2),
            "count": int(mask.sum()),
        })
    calibration = {
        "pred_vs_actual": calib,
        "range_coverage_by_borough": coverage_by_borough,
        "error_by_hour": metrics["error_by_hour"],
    }
    json.dump(calibration, open("models/calibration.json", "w"), indent=2)

    # ---- schema for input validation in the app ----
    schema = {
        "borough": sorted(train["borough"].unique().tolist()),
        "zone": sorted(train["zone"].unique().tolist()),
        "incident_dispatch_area": sorted(train["incident_dispatch_area"].unique().tolist()),
        "initial_call_type": sorted(train["initial_call_type"].unique().tolist()),
        "initial_severity_level_code": sorted(train["initial_severity_level_code"].unique().tolist()),
        "hour": [0, 23], "day_of_week": [0, 6], "month": [1, 12],
        "target": "response_min", "model_version": f"xgb-quantile-2023-{SEED}-wx",
    }
    json.dump(schema, open("models/schema.json", "w"), indent=2)

    # ---- model card ----
    best = max([m for m in metrics["models"] if m["name"].startswith("XGBoost")],
               key=lambda m: -m["mae"])
    metrics["best_model"] = best["name"]
    metrics["beats_baseline"] = best["mae"] < metrics["baseline_mae"]
    json.dump(metrics, open("models/metrics.json", "w"), indent=2)
    print("best model:", best["name"], "beats baseline:", metrics["beats_baseline"])


if __name__ == "__main__":
    main()
