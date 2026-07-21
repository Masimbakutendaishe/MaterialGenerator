"""Celery tasks: async material generation."""
import os
from app.extensions import celery_app, db
from app.models.generation_job import GenerationJob
from app.models.syllabus import Syllabus
from app.models.organization import Organization
from app.services.document_service import build_textbook_docx

GENERATED_FILES_DIR = os.path.join(os.getcwd(), "instance", "generated")


@celery_app.task(name="generate_textbook_task")
def generate_textbook_task(job_id: str):
    """Builds a textbook docx for the given GenerationJob and updates its status.
    File storage is local disk for now — swapped for storage_service (S3/MinIO) once that's built."""
    job = GenerationJob.query.get(job_id)
    if not job:
        return

    job.status = "running"
    db.session.commit()

    try:
        syllabus = Syllabus.query.get(job.syllabus_id)
        organization = Organization.query.get(job.organization_id)
        units = syllabus.content.get("units", [])

        buffer = build_textbook_docx(
            title=syllabus.title,
            units=units,
            organization_name=organization.name if organization else None,
        )

        os.makedirs(GENERATED_FILES_DIR, exist_ok=True)
        file_path = os.path.join(GENERATED_FILES_DIR, f"{job.id}.docx")
        with open(file_path, "wb") as f:
            f.write(buffer.getvalue())

        job.result_file_path = file_path
        job.status = "done"
        db.session.commit()

    except Exception as exc:
        job.status = "failed"
        job.error_message = str(exc)
        db.session.commit()