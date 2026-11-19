# C:\aimlmini\app\__init__.py
"""Application factory for Response Atlas.

Two blueprints: one for pages, one for the JSON API. This keeps page routing
and data endpoints separate, which makes the API easy to test on its own.
"""
import os

# Numpy and scipy reserve memory per BLAS thread when the models load. Cap the
# threads here too, so imports from tests or scripts behave like wsgi.py on a
# machine with limited free memory.
for _name in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ.setdefault(_name, "1")

from flask import Flask, jsonify, send_from_directory

from config import CONFIG_BY_NAME


def create_app(config_name: str = "development") -> Flask:
    app = Flask(__name__)
    app.config.from_object(CONFIG_BY_NAME[config_name])

    # load every artifact once, before serving any request
    from app.services import model_service, stats_service
    model_service.init(app.config["MODEL_DIR"], app.config["PROCESSED_DIR"])
    stats_service.init(app.config["PROCESSED_DIR"])

    from app.routes import pages_bp
    from app.api import api_bp

    app.register_blueprint(pages_bp)
    app.register_blueprint(api_bp, url_prefix="/api")

    @app.route("/geo/<path:name>")
    def geo(name: str):
        """Serve boundary files from data/geo so the map fetches them locally."""
        import os
        return send_from_directory(app.config["GEO_DIR"], name)

    # JSON error responses for wrong API paths, so clients always get JSON there.
    @app.errorhandler(404)
    def not_found(error):  # pragma: no cover - trivial handler
        from flask import request

        if request.path.startswith("/api/"):
            return jsonify({"error": "Not found"}), 404
        return error

    register_health(app)

    return app


def register_health(app: Flask) -> None:
    """Deployment check endpoint. Reports whether required artifact files exist."""
    import os

    @app.route("/health")
    def health():
        model_dir = app.config["MODEL_DIR"]
        geo_dir = app.config["GEO_DIR"]
        artifacts = {
            "p10.joblib": os.path.exists(os.path.join(model_dir, "p10.joblib")),
            "p50.joblib": os.path.exists(os.path.join(model_dir, "p50.joblib")),
            "p90.joblib": os.path.exists(os.path.join(model_dir, "p90.joblib")),
            "schema.json": os.path.exists(os.path.join(model_dir, "schema.json")),
            "zips.geojson": os.path.exists(os.path.join(geo_dir, "zips.geojson")),
        }
        return jsonify({"status": "ok", "artifacts": artifacts})
