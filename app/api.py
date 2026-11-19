# C:\aimlmini\app\api.py
"""JSON API. Reads precomputed files and fitted pipelines, never raw data.

Validation contract: unknown categories and out of range values get HTTP 400
with a plain message. Minutes are rounded to one decimal place in predictions.
"""
import csv
import io

from flask import Blueprint, Response, jsonify, request

from app.services import model_service, stats_service

api_bp = Blueprint("api", __name__)

HOUR_BANDS = ["overnight", "morning", "midday", "evening", "all"]
METRICS = ["median", "p90", "share_over_10", "count"]
HEATMAP_TYPES = ["hour_weekday", "borough_hour", "severity_band"]
BREAKDOWN_TYPES = ["borough", "severity", "call_type"]


def bad(msg: str):
    return jsonify({"error": msg}), 400


@api_bp.route("/ping")
def ping():
    return jsonify({"status": "ok"})


def get_hour_band(args) -> str:
    hb = args.get("hour_band", "all")
    if hb not in HOUR_BANDS:
        raise ValueError(f"hour_band must be one of {HOUR_BANDS}")
    return hb


def get_severity(args) -> str:
    sev = args.get("severity", "all")
    allowed = model_service.schema()["initial_severity_level_code"] + ["all"]
    if sev not in allowed:
        raise ValueError(f"severity must be one of {allowed}")
    return sev


def get_borough(args) -> str:
    b = args.get("borough", "all")
    allowed = model_service.schema()["borough"] + ["all"]
    if b not in allowed:
        raise ValueError(f"borough must be one of {allowed}")
    return b


def get_metric(args) -> str:
    metric = args.get("metric", "median")
    if metric not in METRICS:
        raise ValueError(f"metric must be one of {METRICS}")
    return metric


# ---------- pages and tables ----------


@api_bp.route("/zones")
def zones():
    try:
        hb = get_hour_band(request.args)
        sev = get_severity(request.args)
        metric = get_metric(request.args)
    except ValueError as e:
        return bad(str(e))
    rows = stats_service.get_zones(hb, sev)
    zones_out = []
    for r in rows:
        zones_out.append({
            "zone": r["zone"], "count": r["count"], "median": r["median"],
            "p90": r["p90"], "share_over_10": r["share_over_10"],
            "sparse": r["count"] < stats_service.MIN_ZONE_INCIDENTS,
        })
    return jsonify({
        "hour_band": hb, "severity": sev, "metric": metric,
        "summary": stats_service.get_summary(hb, sev),
        "min_incidents": stats_service.MIN_ZONE_INCIDENTS,
        "zones": zones_out,
    })


@api_bp.route("/hourly")
def hourly():
    try:
        b = get_borough(request.args)
    except ValueError as e:
        return bad(str(e))
    recs = stats_service.get_hourly(b)
    return jsonify({"borough": b, "records": sorted(recs, key=lambda r: r["hour"])})


@api_bp.route("/heatmap")
def heatmap():
    kind = request.args.get("type", "hour_weekday")
    if kind not in HEATMAP_TYPES:
        return bad(f"type must be one of {HEATMAP_TYPES}")
    return jsonify({"type": kind, "records": stats_service.get_heatmap(kind)})


@api_bp.route("/trend")
def trend():
    try:
        b = get_borough(request.args)
    except ValueError as e:
        return bad(str(e))
    return jsonify({"borough": b, "records": stats_service.get_trend(b)})


@api_bp.route("/zone_trend")
def zone_trend():
    return jsonify({"zone_trend": stats_service.get_zone_trend()})


@api_bp.route("/breakdown")
def breakdown():
    kind = request.args.get("by", "borough")
    if kind not in BREAKDOWN_TYPES:
        return bad(f"by must be one of {BREAKDOWN_TYPES}")
    return jsonify({"by": kind, "records": stats_service.get_breakdown(kind)})


@api_bp.route("/distribution")
def distribution():
    try:
        b = get_borough(request.args)
    except ValueError as e:
        return bad(str(e))
    dist = stats_service.get_distribution(b)
    if dist is None:
        return bad(f"no distribution data for borough {b}")
    return jsonify({"borough": b, **dist})


@api_bp.route("/weather_effect")
def weather_effect():
    data = stats_service.get_weather_effect()
    if data is None:
        return bad("weather effect data is not available")
    return jsonify(data)


# ---------- prediction ----------


def validate_case(data: dict, prefix: str = "") -> dict:
    """Check one prediction case against the schema. Returns the clean dict."""
    def field(name: str):
        # prefix only labels errors for compare requests, the payload is nested
        if name not in data:
            raise ValueError(f"{prefix}{name} is required")
        return data[name]

    schema = model_service.schema()
    crosswalk = model_service.crosswalk()

    borough = field("borough")
    if borough not in schema["borough"]:
        raise ValueError(f"borough must be one of {schema['borough']}")

    zipcode = str(field("zipcode"))
    if zipcode not in crosswalk["zip_to_zone"]:
        raise ValueError(f"zipcode {zipcode} is not a known New York City zip code")

    try:
        hour = int(field("hour"))
        day_of_week = int(field("day_of_week"))
    except (TypeError, ValueError):
        raise ValueError("hour and day_of_week must be integers")
    if not 0 <= hour <= 23:
        raise ValueError("hour must be between 0 and 23")
    if not 0 <= day_of_week <= 6:
        raise ValueError("day_of_week must be between 0 and 6")

    severity = str(field("severity"))
    if severity not in schema["initial_severity_level_code"]:
        raise ValueError(f"severity must be one of {schema['initial_severity_level_code']}")

    call_type = field("call_type")
    if call_type not in schema["initial_call_type"]:
        raise ValueError(f"call_type must be one of {schema['initial_call_type']}")

    return {"borough": borough, "zipcode": zipcode, "hour": hour,
            "day_of_week": day_of_week, "severity": severity, "call_type": call_type}


@api_bp.route("/predict", methods=["POST"])
def predict():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return bad("request body must be a JSON object")
    try:
        case = validate_case(data)
    except ValueError as e:
        return bad(str(e))

    result = model_service.predict_case(case)

    # zone median and count come from the saved zone statistics
    zone_rows = {r["zone"]: r for r in stats_service.get_zones("all", "all")}
    zr = zone_rows.get(result["zone"], {})
    result["zone_median"] = zr.get("median")
    result["zone_count"] = zr.get("count")
    return jsonify(result)


@api_bp.route("/explain", methods=["POST"])
def explain():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return bad("request body must be a JSON object")
    try:
        case = validate_case(data)
    except ValueError as e:
        return bad(str(e))
    return jsonify(model_service.explain_case(case))


@api_bp.route("/compare", methods=["POST"])
def compare():
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or "case_a" not in data or "case_b" not in data:
        return bad("request body must be a JSON object with case_a and case_b")
    try:
        a = validate_case(data["case_a"], "case_a.")
        b = validate_case(data["case_b"], "case_b.")
    except ValueError as e:
        return bad(str(e))
    ra = model_service.predict_case(a)
    rb = model_service.predict_case(b)
    return jsonify({
        "case_a": ra, "case_b": rb,
        "difference_p50": round(rb["p50"] - ra["p50"], 1),
        "difference_p90": round(rb["p90"] - ra["p90"], 1),
    })


# ---------- model artifacts ----------


@api_bp.route("/metrics")
def metrics():
    m = model_service.metrics()
    return jsonify({
        "models": [{k: v for k, v in mrow.items() if not k.startswith("_")} for mrow in m["models"]],
        "best_model": m["best_model"], "beats_baseline": m["beats_baseline"],
        "baseline_mae": m["baseline_mae"], "range_coverage": m["range_coverage"],
        "feature_importance": m["feature_importance"],
        "shap_top_features": m.get("shap_top_features"),
        "top_drivers_plain": m.get("top_drivers_plain"),
        "error_by_borough": m.get("error_by_borough"),
        "error_by_hour": m.get("error_by_hour"),
        "error_by_severity": m.get("error_by_severity"),
        "weather_experiment": m.get("weather_experiment"),
    })


@api_bp.route("/calibration")
def calibration():
    return jsonify(model_service.calibration())


@api_bp.route("/modelcard")
def modelcard():
    return jsonify(stats_service.build_model_card())


@api_bp.route("/zone/<zone>")
def zone_detail(zone):
    """24 hour profile for one zone, used by the Overview side panel."""
    hourly = stats_service.get_zone_hourly(zone)
    if not hourly:
        return bad(f"zone {zone} is not in the data")
    zone_rows = {r["zone"]: r for r in stats_service.get_zones("all", "all")}
    zr = zone_rows.get(zone, {})
    return jsonify({
        "zone": zone, "median": zr.get("median"), "p90": zr.get("p90"),
        "count": zr.get("count"), "share_over_10": zr.get("share_over_10"),
        "hourly": sorted(hourly, key=lambda r: r["hour"]),
    })


@api_bp.route("/export/zones.csv")
def export_zones():
    try:
        hb = get_hour_band(request.args)
        sev = get_severity(request.args)
        metric = get_metric(request.args)
    except ValueError as e:
        return bad(str(e))
    rows = stats_service.get_zones(hb, sev)
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["zone", "hour_band", "severity", "count", "median_min",
                     "p90_min", "share_over_10_min"])
    for r in rows:
        sparse = r["count"] < stats_service.MIN_ZONE_INCIDENTS
        writer.writerow([
            r["zone"], hb, sev, r["count"],
            "" if sparse else r["median"],
            "" if sparse else r["p90"],
            "" if sparse else r["share_over_10"],
        ])
    resp = Response(out.getvalue(), mimetype="text/csv")
    resp.headers["Content-Disposition"] = "attachment; filename=zones.csv"
    return resp
