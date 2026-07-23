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

from app.services.assessment_service import build_assessment_docx
from app.models.material_package import MaterialPackage

# Maps a document_subtype to (builder_function, file_extension, content_type)
DOCUMENT_BUILDERS = {
    "textbook": (build_textbook_docx, "docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
    "presentation": (build_presentation_pptx, "pptx", "application/vnd.openxmlformats-officedocument.presentationml.presentation"),
    "assessment": (build_assessment_docx, "docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
}


@celery_app.task(name="generate_package_document_task")
def generate_package_document_task(job_id: str):
    """Generates one document within a MaterialPackage, using the builder registered
    for its document_subtype. This is the generalized version of the two task-specific
    functions above — new document types just need an entry in DOCUMENT_BUILDERS."""
    job = GenerationJob.query.get(job_id)
    if not job:
        return

    job.status = "running"
    db.session.commit()

    try:
        subtype = job.document_subtype
        if subtype not in DOCUMENT_BUILDERS:
            raise ValueError(f"No builder registered for document_subtype '{subtype}'")

        builder_fn, ext, content_type = DOCUMENT_BUILDERS[subtype]

        syllabus = Syllabus.query.get(job.syllabus_id)
        organization = Organization.query.get(job.organization_id)
        units = syllabus.content.get("units", [])
        accreditation = syllabus.accreditation_info or {}

        logo_bytes = None
        if organization and organization.logo_url:
            logo_bytes = download_file(organization.logo_url) or None

        # Presentation builder has a slightly different signature (no seta/nqf on some params) —
        # both builders accept these kwargs, so a single call shape works for textbook/assessment/presentation
        buffer = builder_fn(
            title=syllabus.title,
            units=units,
            organization_name=organization.name if organization else None,
            seta=accreditation.get("seta"),
            nqf_level=accreditation.get("nqf_level"),
            logo_bytes=logo_bytes,
            brand_colors=organization.brand_colors if organization else None,
        )

        storage_key = f"{job.organization_id}/{job.package_id}/{subtype}.{ext}"
        upload_file(file_bytes=buffer.getvalue(), key=storage_key, content_type=content_type)

        job.result_file_path = storage_key
        job.status = "done"

        if job.triggered_by_user_id:
            db.session.add(Notification(
                recipient_user_id=job.triggered_by_user_id,
                message=f'Your {subtype.replace("_", " ")} for "{syllabus.title}" is ready.',
                link_job_id=job.id,
            ))
        db.session.commit()

    except Exception as exc:
        job.status = "failed"
        job.error_message = str(exc)
        db.session.commit()