# Config classes: DevelopmentConfig, TestingConfig, ProductionConfig
"""Config classes for each environment. Never hardcode secrets here — always from env vars."""
import os
from dotenv import load_dotenv
from datetime import timedelta

load_dotenv()


class BaseConfig:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-key-change-me")
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", "postgresql+psycopg://postgres:postgres@localhost:5432/seta_materials"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "dev-jwt-key-change-me")
    CELERY_BROKER_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    CELERY_RESULT_BACKEND = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    S3_ENDPOINT_URL = os.environ.get("S3_ENDPOINT_URL")
    S3_ACCESS_KEY = os.environ.get("S3_ACCESS_KEY")
    S3_SECRET_KEY = os.environ.get("S3_SECRET_KEY")
    S3_BUCKET = os.environ.get("S3_BUCKET", "materials")
    ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
    GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
    UNSPLASH_ACCESS_KEY = os.environ.get("UNSPLASH_ACCESS_KEY")
    GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
    NYRA_API_KEY = os.environ.get("NYRA_API_KEY")
    PERMANENT_SESSION_LIFETIME = timedelta(minutes=20)
    


class DevelopmentConfig(BaseConfig):
    DEBUG = True


class TestingConfig(BaseConfig):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"


class ProductionConfig(BaseConfig):
    DEBUG = False
    # In production, SECRET_KEY / JWT_SECRET_KEY must be set via env — no fallback allowed
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True


config_by_name = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}
