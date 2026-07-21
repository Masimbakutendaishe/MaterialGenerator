"""Application factory — create_app() builds and configures the Flask app."""
import os
from flask import Flask
from flask_talisman import Talisman
from app import models  # noqa: F401 — ensures models are registered with SQLAlchemy
from app.config import config_by_name
from app.extensions import db, migrate, jwt, login_manager, limiter, celery_app


def create_app(config_name=None):
    config_name = config_name or os.environ.get("FLASK_ENV", "development")
    app = Flask(__name__)
    app.config.from_object(config_by_name[config_name])

    # Extensions
    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)
    login_manager.init_app(app)
    limiter.init_app(app)

    # Talisman: security headers (HTTPS enforcement, CSP) — relaxed in dev, strict in prod
    Talisman(app, force_https=(config_name == "production"))

    # Celery config (tasks run via celery_worker.py, sharing this app's config)
    celery_app.conf.update(
        broker_url=app.config["CELERY_BROKER_URL"],
        result_backend=app.config["CELERY_RESULT_BACKEND"],
    )

    # Blueprints — registered here as each api/ module is built
    from app.api.auth import auth_bp
    from app.api.organizations import organizations_bp
    from app.api.syllabus import syllabus_bp
    from app.api.materials import materials_bp
    from app.api.admin import admin_bp
    from app.api.reviews import reviews_bp
    
    app.register_blueprint(reviews_bp, url_prefix="/api/reviews")
    app.register_blueprint(admin_bp, url_prefix="/api/admin")
    app.register_blueprint(auth_bp, url_prefix="/api/auth")
    app.register_blueprint(organizations_bp, url_prefix="/api/organizations")
    app.register_blueprint(syllabus_bp, url_prefix="/api/syllabus")
    app.register_blueprint(materials_bp, url_prefix="/api/materials")

    # Bind Celery tasks to this app's context so db/config are available inside tasks
    class ContextTask(celery_app.Task):
        def __call__(self, *args, **kwargs):
            with app.app_context():
                return self.run(*args, **kwargs)

    celery_app.Task = ContextTask

    return app