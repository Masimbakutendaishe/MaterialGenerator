"""Celery entrypoint — run with: celery -A celery_worker.celery_app worker --loglevel=info --pool=solo"""
from app import create_app
from app.extensions import celery_app
from app.tasks import generation_tasks, syllabus_tasks  # noqa: F401 — ensures tasks are registered

flask_app = create_app()
flask_app.app_context().push()