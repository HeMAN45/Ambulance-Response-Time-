# C:\aimlmini\config.py
"""Application configuration, read from environment variables."""
import os


class Config:
    """Base configuration. Flask reads files from app/static, so no extra path setup is needed."""

    SECRET_KEY = os.environ.get("RESPONSE_ATLAS_SECRET_KEY", "dev-only-change-me")
    # Paths to artifacts produced by the ml pipeline. Flask never trains anything,
    # it only reads these files, so they are resolved once at startup.
    BASE_DIR = os.path.abspath(os.path.dirname(__file__))
    MODEL_DIR = os.path.join(BASE_DIR, "models")
    PROCESSED_DIR = os.path.join(BASE_DIR, "data", "processed")
    GEO_DIR = os.path.join(BASE_DIR, "data", "geo")


class DevelopmentConfig(Config):
    DEBUG = True


class ProductionConfig(Config):
    DEBUG = False


CONFIG_BY_NAME = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
}
