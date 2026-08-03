"""One-off script for Railway's Cron Job feature — checks for stuck jobs and re-dispatches
them, then exits. Replaces the always-on Celery Beat service to avoid its continuous cost."""
from app import create_app
from app.extensions import db
from app.models.generation_job import GenerationJob
from app.tasks.generation_tasks import generate_package_document_task
from datetime import datetime, timezone, timedelta

app = create_app()
with app.app_context():
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=10)
    stuck_jobs = GenerationJob.query.filter(
        GenerationJob.status == "queued",
        GenerationJob.created_at < cutoff,
    ).all()

    for job in stuck_jobs:
        print(f"[RECOVERY] Re-dispatching stuck job {job.id} ({job.document_subtype})")
        async_result = generate_package_document_task.delay(job.id)
        job.task_id = async_result.id
        db.session.commit()

    print(f"[RECOVERY] Re-dispatched {len(stuck_jobs)} stuck job(s)")