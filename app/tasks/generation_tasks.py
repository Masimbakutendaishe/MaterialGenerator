"""Celery tasks: async material generation."""
from app.extensions import celery_app, db
from app.models.generation_job import GenerationJob
from app.models.syllabus import Syllabus
from app.models.organization import Organization
from app.services.document_service import build_textbook_docx
from app.services.presentation_service import build_presentation_pptx
from app.services.storage_service import upload_file, download_file
from app.models.review import Notification
from app.services.guide_document_service import build_guide_docx
from functools import partial
from app.services.facilitator_guide_service import build_facilitator_guide_docx
from app.services.summative_assessment_service import build_summative_assessment_docx
from app.services.alignment_matrix_service import build_alignment_matrix_docx
from app.services.poe_guide_service import build_poe_guide_docx
from functools import partial as _partial  # already imported as partial, reuse existing import
from app.services.qcto_knowledge_module_service import build_qcto_knowledge_module_docx_adapter
from app.services.qcto_practical_module_service import build_qcto_practical_module_docx_adapter
from app.services.qcto_workplace_module_service import build_qcto_workplace_module_docx_adapter
from app.services.qcto_workplace_logbook_service import build_qcto_workplace_logbook_docx_adapter
from app.services.qcto_video_guide_service import build_qcto_video_guide_docx_adapter
from app.services.qcto_assessment_service import build_qcto_km_assessment_docx_adapter, build_qcto_pm_assessment_docx_adapter

@celery_app.task(name="generate_textbook_task")
def generate_textbook_task(job_id: str):
    job = GenerationJob.query.get(job_id)
    if not job:
        return

    job.status = "running"
    from datetime import datetime, timezone
    job.started_at = datetime.now(timezone.utc)
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
            job_id=job.id,
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

@celery_app.task(name="recover_stuck_jobs")
def recover_stuck_jobs():
    """Finds jobs stuck in 'queued' for more than 5 minutes with no sign of progress,
    and re-dispatches them. Safety net for tasks lost during worker restarts/deploys,
    even with task_acks_late — covers edge cases like broker-level message loss."""
    from datetime import datetime, timezone, timedelta
    from app.models.generation_job import GenerationJob

    cutoff = datetime.now(timezone.utc) - timedelta(minutes=5)
    stuck_jobs = GenerationJob.query.filter(
        GenerationJob.status == "queued",
        GenerationJob.created_at < cutoff,
    ).all()

    for job in stuck_jobs:
        print(f"[RECOVERY] Re-dispatching stuck job {job.id} ({job.document_subtype})")
        async_result = generate_package_document_task.delay(job.id)
        job.task_id = async_result.id
        db.session.commit()

    if stuck_jobs:
        print(f"[RECOVERY] Re-dispatched {len(stuck_jobs)} stuck job(s)")

@celery_app.task(name="generate_presentation_task")
def generate_presentation_task(job_id: str):
    job = GenerationJob.query.get(job_id)
    if not job:
        return

    job.status = "running"
    from datetime import datetime, timezone
    job.started_at = datetime.now(timezone.utc)
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
            job_id=job.id,
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
    "qcto_knowledge_modules": (build_qcto_knowledge_module_docx_adapter, "docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
    "textbook": (build_textbook_docx, "docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
    "presentation": (build_presentation_pptx, "pptx", "application/vnd.openxmlformats-officedocument.presentationml.presentation"),
    "assessment": (build_assessment_docx, "docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
    "learner_manual": (partial(build_guide_docx, document_subtype="learner_manual"), "docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
    "assessment_guide": (build_facilitator_guide_docx, "docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
    "formative_assessment": (partial(build_assessment_docx, doc_label="Formative Assessment"), "docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
    "summative_assessment": (build_summative_assessment_docx, "docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
    "moderator_guide": (partial(build_guide_docx, document_subtype="moderator_guide"), "docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
    "facilitator_guide": (partial(build_guide_docx, document_subtype="facilitator_guide"), "docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
    "poe_guide": (build_poe_guide_docx, "docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
    "learner_induction_guide": (partial(build_guide_docx, document_subtype="learner_induction_guide"), "docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
    "programme_strategy": (partial(build_guide_docx, document_subtype="programme_strategy"), "docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
    "programme_alignment_matrix": (build_alignment_matrix_docx, "docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
    "qcto_practical_modules": (build_qcto_practical_module_docx_adapter, "docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
    "qcto_workplace_logbook": (build_qcto_workplace_logbook_docx_adapter, "docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
    "qcto_video_guide": (build_qcto_video_guide_docx_adapter, "docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
    "qcto_km_assessment": (build_qcto_km_assessment_docx_adapter, "docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
    "qcto_pm_assessment": (build_qcto_pm_assessment_docx_adapter, "docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
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
    from datetime import datetime, timezone
    job.started_at = datetime.now(timezone.utc)
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
            job_id=job.id,
        )

        if job.package_id:
            storage_key = f"{job.organization_id}/{job.package_id}/{subtype}.{ext}"
        else:
            storage_key = f"{job.organization_id}/{job.id}.{ext}"
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