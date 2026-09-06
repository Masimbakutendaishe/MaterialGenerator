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
    login_manager.login_view = "web.login"

    @app.before_request
    def refresh_session():
        from flask import session
        if "_user_id" in session:  # only touch the session for logged-in users
            session.permanent = True

    from app.models.user import User

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(user_id)

    limiter.init_app(app)

    from app.extensions import csrf
    csrf.init_app(app)

    # Talisman: security headers (HTTPS enforcement, CSP) — relaxed in dev, strict in prod
    csp = {
        'default-src': "'self'",
        'script-src': [
            "'self'",
            "'unsafe-inline'",
            "https://cdn.tailwindcss.com",
            "https://cdnjs.cloudflare.com",
            "https://static.cloudflareinsights.com",
        ],
        'style-src': ["'self'", "'unsafe-inline'"],  # Tailwind injects styles inline
        'font-src': ["'self'", "data:"],
        'img-src': ["'self'", "data:", "blob:", "http://localhost:9000", "http://127.0.0.1:9000", "https://*.r2.cloudflarestorage.com"],
    }
    Talisman(app, force_https=(config_name == "production"), content_security_policy=csp)

    # Celery config (tasks run via celery_worker.py, sharing this app's config)
    celery_app.conf.update(
        broker_url=app.config["CELERY_BROKER_URL"],
        result_backend=app.config["CELERY_RESULT_BACKEND"],
    )

    # Blueprints — registered here as each api/ or web/ module is built
    from app.api.auth import auth_bp
    from app.api.organizations import organizations_bp
    from app.api.syllabus import syllabus_bp
    from app.api.materials import materials_bp
    from app.api.admin import admin_bp
    from app.api.reviews import reviews_bp
    from app.web.views import web_bp
    from app.web.admin_views import web_admin_bp
    from app.web.syllabus_views import syllabus_web_bp
    from app.web.branding_views import branding_web_bp
    from app.web.generation_views import generation_web_bp
    from app.web.review_views import review_web_bp
    from app.web.search_views import search_web_bp

    app.register_blueprint(search_web_bp)
    app.register_blueprint(review_web_bp)
    app.register_blueprint(generation_web_bp)
    app.register_blueprint(branding_web_bp)
    app.register_blueprint(syllabus_web_bp)
    app.register_blueprint(web_admin_bp)
    app.register_blueprint(web_bp)
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

    from app.services.seta_constants import document_display_name
    app.jinja_env.filters["document_display_name"] = document_display_name


    @app.context_processor
    def inject_nav_avatar():
        from flask_login import current_user
        if current_user.is_authenticated and current_user.profile_picture_url:
            from app.services.storage_service import get_presigned_url
            return {"nav_avatar_url": get_presigned_url(current_user.profile_picture_url, expires_in=300)}
        return {"nav_avatar_url": None}

    return app