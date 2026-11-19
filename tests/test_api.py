# C:\aimlmini\tests\test_api.py
"""Integration tests for every API endpoint, run against the real artifacts.

These tests read the saved models and statistics, so the ml pipeline must have
run first (train.py at minimum). Each endpoint has a happy path test and, where
the contract documents it, a validation test expecting HTTP 400.
"""
import json

import pytest

from app import create_app


@pytest.fixture(scope="session")
def client():
    app = create_app("development")
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.get_json()
    assert body["status"] == "ok"
    assert body["artifacts"]["p50.joblib"] is True


def test_ping(client):
    r = client.get("/api/ping")
    assert r.status_code == 200


def test_zones_default(client):
    r = client.get("/api/zones")
    assert r.status_code == 200
    body = r.get_json()
    assert body["metric"] == "median"
    assert len(body["zones"]) > 100
    assert body["summary"]["median"] > 0
    assert all("sparse" in z for z in body["zones"])


def test_zones_with_filters(client):
    r = client.get("/api/zones?hour_band=evening&severity=1&metric=p90")
    assert r.status_code == 200
    body = r.get_json()
    assert body["hour_band"] == "evening" and body["severity"] == "1"
    assert len(body["zones"]) > 0


def test_zones_bad_metric(client):
    assert client.get("/api/zones?metric=bogus").status_code == 400


def test_zones_bad_hour_band(client):
    assert client.get("/api/zones?hour_band=noon").status_code == 400


def test_hourly(client):
    r = client.get("/api/hourly?borough=Brooklyn")
    assert r.status_code == 200
    recs = r.get_json()["records"]
    assert len(recs) == 24
    assert recs[0]["hour"] == 0


def test_hourly_bad_borough(client):
    assert client.get("/api/hourly?borough=Paris").status_code == 400


VALID_CASE = {
    "borough": "Brooklyn", "zipcode": "11226", "hour": 18,
    "day_of_week": 4, "severity": "3", "call_type": "CARD",
}


def test_predict_valid(client):
    r = client.post("/api/predict", json=VALID_CASE)
    assert r.status_code == 200
    body = r.get_json()
    assert body["p10"] <= body["p50"] <= body["p90"]
    assert body["zone_median"] is not None
    assert "model_version" in body
    assert round(body["p50"], 1) == body["p50"]


def test_predict_unknown_borough(client):
    bad_case = {**VALID_CASE, "borough": "Paris"}
    r = client.post("/api/predict", json=bad_case)
    assert r.status_code == 400
    assert "borough" in r.get_json()["error"]


def test_predict_unknown_zip(client):
    bad_case = {**VALID_CASE, "zipcode": "99999"}
    r = client.post("/api/predict", json=bad_case)
    assert r.status_code == 400


def test_predict_hour_out_of_range(client):
    bad_case = {**VALID_CASE, "hour": 24}
    assert client.post("/api/predict", json=bad_case).status_code == 400


def test_predict_unknown_call_type(client):
    bad_case = {**VALID_CASE, "call_type": "PIZZA"}
    assert client.post("/api/predict", json=bad_case).status_code == 400


def test_predict_missing_field(client):
    r = client.post("/api/predict", json={"borough": "Brooklyn"})
    assert r.status_code == 400
    assert "required" in r.get_json()["error"]


def test_predict_non_json(client):
    r = client.post("/api/predict", data="not json", content_type="text/plain")
    assert r.status_code == 400


def test_explain_valid(client):
    r = client.post("/api/explain", json=VALID_CASE)
    assert r.status_code == 200
    body = r.get_json()
    # base value plus contributions roughly rebuilds the estimate
    total = body["base_value"] + sum(c["contribution"] for c in body["contributions"])
    assert abs(total - body["p50"]) < 1.0
    assert len(body["contributions"]) >= 5


def test_compare_valid(client):
    other = {**VALID_CASE, "hour": 3, "zipcode": "10036", "borough": "Manhattan"}
    r = client.post("/api/compare", json={"case_a": VALID_CASE, "case_b": other})
    assert r.status_code == 200
    body = r.get_json()
    assert abs(body["difference_p50"] - (body["case_b"]["p50"] - body["case_a"]["p50"])) < 0.15


def test_compare_missing_case(client):
    r = client.post("/api/compare", json={"case_a": VALID_CASE})
    assert r.status_code == 400


def test_metrics(client):
    r = client.get("/api/metrics")
    assert r.status_code == 200
    body = r.get_json()
    assert len(body["models"]) >= 4
    assert body["beats_baseline"] is True
    assert 0 < body["range_coverage"] < 1
    assert len(body["feature_importance"]) > 0
    assert body["weather_experiment"]["kept"] is True


def test_calibration(client):
    r = client.get("/api/calibration")
    assert r.status_code == 200
    body = r.get_json()
    assert len(body["pred_vs_actual"]) == 10
    assert "range_coverage_by_borough" in body


def test_modelcard(client):
    r = client.get("/api/modelcard")
    assert r.status_code == 200
    body = r.get_json()
    assert body["data_source"].startswith("NYC EMS")
    assert body["row_counts"]["test_rows"] > 0
    assert len(body["known_weaknesses"]) >= 3


def test_heatmap_hour_weekday(client):
    r = client.get("/api/heatmap?type=hour_weekday")
    assert r.status_code == 200
    assert len(r.get_json()["records"]) == 24 * 7


def test_heatmap_bad_type(client):
    assert client.get("/api/heatmap?type=x").status_code == 400


def test_trend(client):
    r = client.get("/api/trend?borough=all")
    assert r.status_code == 200
    assert len(r.get_json()["records"]) >= 12


def test_zone_trend(client):
    r = client.get("/api/zone_trend")
    assert r.status_code == 200
    assert len(r.get_json()["zone_trend"]) > 100


def test_breakdown(client):
    r = client.get("/api/breakdown?by=call_type")
    assert r.status_code == 200
    assert len(r.get_json()["records"]) > 5
    assert client.get("/api/breakdown?by=color").status_code == 400


def test_distribution(client):
    r = client.get("/api/distribution?borough=all")
    assert r.status_code == 200
    body = r.get_json()
    assert len(body["bins"]) == 30


def test_weather_effect(client):
    r = client.get("/api/weather_effect")
    assert r.status_code == 200
    body = r.get_json()
    assert body["kept"] is True
    assert len(body["precipitation"]) > 0
    assert len(body["snow"]) >= 1


def test_zone_detail(client):
    r = client.get("/api/zone/11226")
    assert r.status_code == 200
    body = r.get_json()
    assert len(body["hourly"]) > 12
    assert client.get("/api/zone/99999").status_code == 400


def test_export_zones_csv(client):
    r = client.get("/api/export/zones.csv?hour_band=all&severity=all")
    assert r.status_code == 200
    assert r.mimetype == "text/csv"
    lines = r.get_data(as_text=True).strip().splitlines()
    assert lines[0].startswith("zone,hour_band,severity")
    assert len(lines) > 100


def test_export_sparse_zones_blanked(client):
    r = client.get("/api/export/zones.csv?hour_band=all&severity=8")
    body = r.get_data(as_text=True).strip().splitlines()
    sparse_rows = [line for line in body[1:] if line.endswith(",,")]
    assert len(sparse_rows) > 0
