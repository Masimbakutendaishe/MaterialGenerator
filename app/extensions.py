# db, migrate, jwt, limiter, celery instances (no circular imports)
"""Shared extension instances — imported by app/__init__.py and models/services."""
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_jwt_extended import JWTManager
from flask_login import LoginManager
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from celery import Celery
from flask_wtf import CSRFProtect


csrf = CSRFProtect()
db = SQLAlchemy()
migrate = Migrate()
jwt = JWTManager()
login_manager = LoginManager()
limiter = Limiter(key_func=get_remote_address)
celery_app = Celery(__name__)
celery_app.conf.update(
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    broker_connection_retry_on_startup=True,
    task_reject_on_worker_lost=True,
    beat_schedule={
        "recover-stuck-jobs": {
            "task": "recover_stuck_jobs",
            "schedule": 180.0,
        },
    },
)