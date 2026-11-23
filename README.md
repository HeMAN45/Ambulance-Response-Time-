# Response Atlas

Response Atlas is a Flask web application that shows how long ambulances take to reach patients across New York City, and predicts the response time for a chosen zone, day and hour. It is built from one year of NYC EMS incident dispatch data.

## The problem

Response time varies by place, hour and severity, but planners cannot see the pattern or estimate it quickly. Response Atlas shows where and when response is slow, estimates a likely range for a case, and explains what drives the estimate.

## Pages

- `/` Overview: choropleth map, hour band and severity filters, four summary figures, four hour band maps, a difference map, an incident volume view, a zone panel and a sortable zone table with CSV export.
- `/predict` Predict: a form for borough, zip, hour, day, severity and call type, a result with a 10th to 90th percentile range, a comparison with the zone median, a waterfall explanation, a two case comparison, a 24 hour zone profile, the zone monthly trend and a comparison with the borough and city medians.
- `/insights` Insights: hour and weekday heatmaps, weather and holiday effects, model comparison, feature importance and the supporting charts, grouped under When, Where, What and Model.
- `/method` Method: the model card, calibration checks, leakage rules, features and limitations.
- `/styleguide` Style test: an internal page that shows every design token and component. It is not linked from the navigation.

## Data

- Source: NYC EMS Incident Dispatch Data, FDNY, NYC Open Data, dataset `76xm-jjuj`.
- Dataset page: https://data.cityofnewyork.us/d/76xm-jjuj
- Year: 2023.
- The downloader keeps every fourth calendar day, which gives 371,869 rows. Filters keep 350,253 rows with a valid response time at or below 60 minutes.
- Place is known only at borough, zip code and dispatch area level. Exact incident locations are not published.
- Zones are zip codes grouped into MODZCTA areas. Boundaries come from the NYC modified zip code tabulation areas and borough boundary files.
- Weather: one citywide hourly series for 2023 from the Open Meteo archive API, with temperature, precipitation and snowfall. A US holiday flag comes from the `holidays` package.

## Method

The target is `response_min`, which is `incident_response_seconds_qy` divided by 60. Rows with an invalid response flag, a null target, or a value above 60 minutes are removed, and the count removed at each step is written to `data/processed/clean_report.json`.

Features:

- Time: hour, day of week (Monday is 0), month, weekend flag, hour band.
- Place: borough, zip zone, dispatch area.
- Incident: initial call type, initial severity level.
- Weather: citywide temperature, precipitation, snowfall, snow flag and holiday flag.

Leakage rules:

- No dispatch, travel or assignment timestamps are used. They are recorded after the call and are part of the target.
- Only initial call type and initial severity are used, never the final versions.
- All aggregates were computed from the training period only.
- The split is by time: the oldest 80 percent of incidents train, the newest 20 percent test.

Models: a median by borough and hour baseline, Ridge regression, Random Forest and XGBoost. Three XGBoost quantile models produce the 10th, 50th and 90th percentile estimates. Preprocessing and the model live in one scikit learn Pipeline, so the web app applies the same encoding as training. Feature contributions come from the p50 model's built in `pred_contribs` output, with one hot columns added back under their original feature names.

## Results

Test period: 2023-10-20 to 2023-12-28. Train rows 280,202. Test rows 70,051.

| Model | MAE, min | RMSE, min | R2 | Within 2 min |
| --- | ---: | ---: | ---: | ---: |
| Baseline, median by borough and hour | 6.005 | 10.208 | -0.117 | 32.9% |
| Ridge regression | 5.572 | 8.836 | 0.163 | 29.7% |
| Random Forest | 5.414 | 8.908 | 0.149 | 34.4% |
| XGBoost | 5.273 | 8.489 | 0.227 | 33.9% |

The 50th percentile quantile model has a test MAE of 5.410 minutes. The 10th to 90th percentile range covers 73.9 percent of test cases, below the expected 80 percent, so the Method page reports the measured share rather than claiming 80.

Weather and holiday features lowered test MAE from 5.452 to 5.273 minutes on the same split, so the production pipeline keeps them. The comparison is stored in `models/metrics.json`.

Mean absolute error by borough, in minutes: Bronx 6.37, Brooklyn 4.92, Manhattan 6.25, Queens 4.49, Richmond and Staten Island 3.61.

Top drivers from the explanation sample of 5,000 test rows: severity, hour of day, month, temperature and dispatch area. The full ranking is in `models/metrics.json`.

## Run the app

The repository includes the trained models and processed statistics, so the app runs without retraining. Use the pipeline below to rebuild them.

Windows PowerShell:

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
python wsgi.py
```

The site is then at http://127.0.0.1:5000

Other systems:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python wsgi.py
```

Production uses gunicorn on a Linux host:

```bash
gunicorn wsgi:app
```

Configuration is read from environment variables. `RESPONSE_ATLAS_SECRET_KEY` sets the Flask secret key. `create_app` accepts `development` or `production`.

## Rebuild the data and models

Install the training and testing dependencies with `python -m pip install -r requirements-dev.txt`.

Run these from the repository root, in this order. The scripts read and write relative paths under `data/`, `models/` and `tmp/`.

```bash
python ml/download.py
python ml/clean.py
python ml/weather.py
python ml/features.py
python ml/train.py
python ml/weather_experiment.py
python ml/explain.py
python ml/build_lookup.py
python ml/build_stats.py
```

Notes:

- `ml/download.py` needs internet access to the NYC Open Data API.
- `ml/weather.py` needs internet access to the Open Meteo archive API. It writes `data/processed/weather_2023.csv`, `data/processed/weather_stats.json` and `data/processed/weather_monthly.json`. The monthly file holds the twelve temperature defaults used by the predict form, so the app does not read the full hourly CSV at startup.
- `ml/features.py` merges the weather series into the feature tables, so `weather.py` runs before it.
- `ml/clean.py` and `ml/build_stats.py` read the raw boundary files `tmp/modzcta_raw.geojson` and `tmp/boroughs_raw.geojson`. Both files are already present in this working copy.
- `ml/train.py` writes `models/p10.joblib`, `p50.joblib`, `p90.joblib`, `schema.json`, `metrics.json` and `calibration.json`.
- `ml/weather_experiment.py` must run after `train.py`, because `train.py` rewrites `metrics.json`. It adds the with and without weather comparison.
- `ml/explain.py` adds the feature importance and top driver lists to `metrics.json`.
- `ml/build_lookup.py` writes `data/processed/zip_crosswalk.json`.
- `ml/build_stats.py` writes the statistics files under `data/processed/` and the simplified boundaries under `data/geo/`.

## Tests

The API tests run against the real saved artifacts.

```bash
python -m pytest
```

## API

| Endpoint | Method | Purpose |
| --- | --- | --- |
| `/api/zones` | GET | Zone statistics for an hour band and severity, with a metric choice |
| `/api/hourly` | GET | Median and 90th percentile for each hour, optional borough |
| `/api/predict` | POST | p10, p50 and p90 for one case |
| `/api/explain` | POST | Base value and feature contributions for one case |
| `/api/compare` | POST | Two cases, both predictions and the differences |
| `/api/heatmap` | GET | H1 to H3 grid values |
| `/api/trend` | GET | Monthly median and 90th percentile, optional borough |
| `/api/zone_trend` | GET | Monthly trend for every zone, used by the ranking sparklines |
| `/api/breakdown` | GET | Statistics by borough, severity or call type |
| `/api/distribution` | GET | Response time histogram bins, optional borough |
| `/api/weather_effect` | GET | Median by precipitation band, snow and holiday flag |
| `/api/zone/<zone>` | GET | 24 hour profile for one zone |
| `/api/metrics` | GET | Model comparison and feature importance |
| `/api/calibration` | GET | Calibration and coverage data |
| `/api/modelcard` | GET | Model card content |
| `/api/export/zones.csv` | GET | CSV of the zone table for the current filters |
| `/api/ping` | GET | Simple health check |
| `/health` | GET | Deployment check for required artifact files |

Unknown categories and out of range values return HTTP 400 with a plain message. Prediction minutes are rounded to one decimal place. Models and statistics load once at startup, never per request.

## Project structure

```text
app/
  __init__.py          application factory, blueprint registration, health
  routes.py            page routes
  api.py               JSON API
  services/
    model_service.py   loads pipelines and artifacts, serves predictions
    stats_service.py   reads precomputed statistics, builds the model card
  templates/           base layout and the four pages
  static/
    css/               design tokens and styles
    js/                plain ES modules, one file per page
    vendor/            local Leaflet and ECharts
    fonts/             self hosted woff2 files
data/
  raw/                 downloaded incident data
  processed/           cleaned data and statistics
  geo/                 simplified boundaries
ml/                    download, clean, weather, features, train, experiment, explain, stats
models/                fitted pipelines, schema, metrics, calibration
tests/                 API integration tests
config.py              environment based configuration
wsgi.py                entry point
requirements.txt       pinned packages
```

## Limitations

- One citywide model. Weather is a single citywide series, not local conditions at the incident.
- Predictions assume a dry non holiday day at the 2023 average temperature for the current month, because the form does not collect weather.
- Predictions assume the current month for the month feature.
- Some zones have few incidents and wide uncertainty. Zones below 30 incidents are shown as not enough data on the map.
- The model estimates a distribution level response time, not the outcome of a single dispatch.
- It is intended for planning and analysis, not for live dispatch decisions, and it makes no clinical or operational claims.

## Screenshots

Add screenshots of the four pages here after running the site locally. The repository does not include generated images.
