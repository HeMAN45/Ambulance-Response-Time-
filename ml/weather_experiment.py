# C:\aimlmini\ml\weather_experiment.py
"""Compare XGBoost test MAE with and without weather and holiday features.

Both runs use the same time split and the same settings, so the difference is
only the extra columns. The result and the keep or drop decision are written to
models/metrics.json. features.py must have merged the weather columns first.
"""
import json
import os

# Cap BLAS threads before numpy and xgboost load, the experiment runs on a
# machine with limited free memory.
for _name in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ.setdefault(_name, "1")

import pandas as pd
import xgboost as xgb
from sklearn.compose import ColumnTransformer
from sklearn.metrics import mean_absolute_error
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

TRAIN = "data/processed/train.csv"
TEST = "data/processed/test.csv"
METRICS = "models/metrics.json"
WEATHER_STATS = "data/processed/weather_stats.json"

CAT_COLS = ["hour_band", "borough", "zone", "incident_dispatch_area",
            "initial_call_type", "initial_severity_level_code"]
NUM_COLS = ["hour", "day_of_week", "month", "weekend"]
WEATHER_NUM = ["temperature_2m", "precipitation", "snowfall", "is_snow", "holiday"]
TARGET = "response_min"
SEED = 42


def load(path: str) -> pd.DataFrame:
    df = pd.read_csv(path, dtype={c: str for c in CAT_COLS})
    for c in NUM_COLS:
        df[c] = pd.to_numeric(df[c]).astype(int)
    for c in WEATHER_NUM:
        df[c] = pd.to_numeric(df[c])
    df["initial_severity_level_code"] = df["initial_severity_level_code"].astype(str)
    return df


def preprocessor(num_cols: list[str]) -> ColumnTransformer:
    return ColumnTransformer(
        [("cat", OneHotEncoder(handle_unknown="ignore"), CAT_COLS),
         ("num", "passthrough", num_cols)],
        remainder="drop",
    )


def fit_mae(train: pd.DataFrame, test: pd.DataFrame, num_cols: list[str]) -> float:
    features = CAT_COLS + num_cols
    pipe = Pipeline([
        ("prep", preprocessor(num_cols)),
        ("model", xgb.XGBRegressor(
            n_estimators=400, learning_rate=0.08, max_depth=8,
            subsample=0.9, colsample_bytree=0.9,
            tree_method="hist", random_state=SEED, n_jobs=2)),
    ])
    pipe.fit(train[features], train[TARGET])
    pred = pipe.predict(test[features])
    return float(mean_absolute_error(test[TARGET], pred))


def main() -> None:
    train, test = load(TRAIN), load(TEST)
    without = fit_mae(train, test, NUM_COLS)
    with_weather = fit_mae(train, test, NUM_COLS + WEATHER_NUM)
    improved = with_weather < without
    print(f"without weather MAE: {without:.4f}")
    print(f"with weather MAE:    {with_weather:.4f}")
    print(f"improved: {improved}")

    metrics = json.load(open(METRICS))
    metrics["weather_experiment"] = {
        "without_mae": round(without, 3),
        "with_mae": round(with_weather, 3),
        "improved": bool(improved),
        "kept": bool(improved),
        "features": WEATHER_NUM,
        "source": "Open Meteo archive API, one citywide hourly series for New York City, 2023",
        "holiday_source": "holidays package, US calendar, 2023",
        "decision": "kept" if improved else "dropped",
        "note": (
            "Weather and holiday features lowered test MAE, so the production pipeline keeps them."
            if improved else
            "Weather and holiday features did not lower test MAE, so the production pipeline drops them."
        ),
    }
    json.dump(metrics, open(METRICS, "w"), indent=2)

    stats = json.load(open(WEATHER_STATS))
    stats["kept"] = bool(improved)
    json.dump(stats, open(WEATHER_STATS, "w"), indent=2)


if __name__ == "__main__":
    main()
