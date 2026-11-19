# C:\aimlmini\app\routes.py
"""Page routes. One route per page, each rendering a template that extends base.html."""
import json
import os

from flask import Blueprint, render_template

pages_bp = Blueprint("pages", __name__)


def _schema_json():
    from flask import current_app
    path = os.path.join(current_app.config["MODEL_DIR"], "schema.json")
    return json.load(open(path))


def _crosswalk_json():
    from flask import current_app
    path = os.path.join(current_app.config["PROCESSED_DIR"], "zip_crosswalk.json")
    return json.load(open(path))


@pages_bp.route("/")
def overview():
    return render_template("overview.html", active_page="overview")


@pages_bp.route("/predict")
def predict():
    schema = _schema_json()
    xw = _crosswalk_json()
    # zip options grouped by borough, from the zone metadata in the boundary data
    zips_by_borough = {}
    for z, zone in xw["zip_to_zone"].items():
        b = xw["zone_to_borough"].get(zone)
        # Some boundary features have no borough, so only group real names.
        if isinstance(b, str) and b:
            zips_by_borough.setdefault(b, set()).add(z)
    return render_template(
        "predict.html", active_page="predict", schema=schema,
        zips_by_borough={b: sorted(v) for b, v in zips_by_borough.items()},
    )


@pages_bp.route("/insights")
def insights():
    return render_template("insights.html", active_page="insights")


@pages_bp.route("/method")
def method():
    return render_template("method.html", active_page="method")


@pages_bp.route("/styleguide")
def styleguide():
    """Internal page that shows every design token and component in one place."""
    from app.services import stats_service
    summary = stats_service.get_summary("all", "all")
    zones = sorted(stats_service.get_zones("all", "all"), key=lambda r: -r["median"])[:6]
    return render_template("styleguide.html", active_page=None, summary=summary, zones=zones)
