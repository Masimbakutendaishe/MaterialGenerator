"""Celery tasks: async material generation."""
from app.extensions import celery_app, db
from app.models.generation_job import GenerationJob
from app.models.syllabus import Syllabus
from app.models.organization import Organization
from app.services.document_service import build_textbook_docx
from app.services.presentation_service import build_presentation_pptx
from app.services.storage_service import upload_file, download_file
from app.models.review import Notification

@celery_app.task(name="generate_textbook_task")
def generate_textbook_task(job_id: str):
    job = GenerationJob.query.get(job_id)
    if not job:
        return

    job.status = "running"
    db.session.commit()

    try:
        syllabus = Syllabus.query.get(job.syllabus_id)
        organization = Organization.query.get(job.organization_id)
        units = syllabus.content.get("units", [])
        accreditation = syllabus.accreditation_info or {}

        logo_bytes = None
        if organization and organization.logo_url:
            logo_bytes = download_file(organization.logo_url) or None

        buffer = build_textbook_docx(
            title=syllabus.title,
            units=units,
            organization_name=organization.name if organization else None,
            seta=accreditation.get("seta"),
            nqf_level=accreditation.get("nqf_level"),
            logo_bytes=logo_bytes,
            brand_colors=organization.brand_colors if organization else None,
        )

        storage_key = f"{job.organization_id}/{job.id}.docx"
        upload_file(
            file_bytes=buffer.getvalue(),
            key=storage_key,
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )

        job.result_file_path = storage_key
        
        job.status = "done"
        if job.triggered_by_user_id:
            db.session.add(Notification(
                recipient_user_id=job.triggered_by_user_id,
                message=f'Your {job.material_type} "{syllabus.title}" is ready to download.',
                link_job_id=job.id,
            ))
        db.session.commit()

    except Exception as exc:
        job.status = "failed"
        job.error_message = str(exc)
        db.session.commit()


@celery_app.task(name="generate_presentation_task")
def generate_presentation_task(job_id: str):
    job = GenerationJob.query.get(job_id)
    if not job:
        return

    job.status = "running"
    db.session.commit()

    try:
        syllabus = Syllabus.query.get(job.syllabus_id)
        organization = Organization.query.get(job.organization_id)
        units = syllabus.content.get("units", [])
        accreditation = syllabus.accreditation_info or {}

        logo_bytes = None
        if organization and organization.logo_url:
            logo_bytes = download_file(organization.logo_url) or None

        buffer = build_presentation_pptx(
            title=syllabus.title,
            units=units,
            organization_name=organization.name if organization else None,
            brand_colors=organization.brand_colors if organization else None,
            seta=accreditation.get("seta"),
            nqf_level=accreditation.get("nqf_level"),
            logo_bytes=logo_bytes,
        )

        storage_key = f"{job.organization_id}/{job.id}.pptx"
        upload_file(
            file_bytes=buffer.getvalue(),
            key=storage_key,
            content_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        )

        job.result_file_path = storage_key
        job.status = "done"
        if job.triggered_by_user_id:
            db.session.add(Notification(
                recipient_user_id=job.triggered_by_user_id,
                message=f"Your {job.material_type} is ready to download.",
            ))
        db.session.commit()

    except Exception as exc:
        job.status = "failed"
        job.error_message = str(exc)
        db.session.commit()