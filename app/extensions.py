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