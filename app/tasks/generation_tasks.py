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
from app.services.qcto_km_facilitator_guide_service import build_qcto_km_facilitator_guide_docx_adapter
from app.services.qcto_km_assessment_guide_service import build_qcto_km_assessment_guide_docx_adapter
from app.services.qcto_km_poe_service import build_qcto_km_poe_docx_adapter
from app.services.qcto_km_learner_workbook_service import build_qcto_km_learner_workbook_docx_adapter
from app.services.qcto_isa_service import build_qcto_isa_docx_adapter
from app.services.qcto_pm_facilitator_guide_service import build_qcto_pm_facilitator_guide_docx_adapter
from app.services.qcto_pm_assessment_guide_service import build_qcto_pm_assessment_guide_docx_adapter
from app.services.qcto_pm_poe_service import build_qcto_pm_poe_docx_adapter
from app.services.qcto_wm_supervisor_guide_service import build_qcto_wm_supervisor_guide_docx_adapter
from app.services.qcto_final_exam_service import build_qcto_final_exam_docx_adapter
from app.services.qcto_fisa_service import build_qcto_fisa_docx_adapter
from app.services.qcto_learning_matrix_service import build_qcto_learning_matrix_docx_adapter
from app.services.qcto_km_powerpoint_service import build_qcto_km_powerpoint_zip_adapter
from app.services.qcto_pm_powerpoint_service import build_qcto_pm_powerpoint_zip_adapter

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
        if syllabus.syllabus_type == "qcto":
            units = syllabus.content.get("modules", [])
        else:
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
        db.session.expire_all()
        fresh_job = GenerationJob.query.get(job.id)
        if fresh_job and fresh_job.status == "cancelled":
            # Already marked cancelled by the user's Cancel button — don't overwrite
            # with "failed". The task stopped because of _JobCancelledError bubbling up
            # from ai_service.py, not a genuine error.
            return
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
        if syllabus.syllabus_type == "qcto":
            units = syllabus.content.get("modules", [])
        else:
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
        db.session.expire_all()
        fresh_job = GenerationJob.query.get(job.id)
        if fresh_job and fresh_job.status == "cancelled":
            # Already marked cancelled by the user's Cancel button — don't overwrite
            # with "failed". The task stopped because of _JobCancelledError bubbling up
            # from ai_service.py, not a genuine error.
            return
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
    "qcto_workplace_modules": (build_qcto_workplace_module_docx_adapter, "docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
    "qcto_video_guide": (build_qcto_video_guide_docx_adapter, "docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
    "qcto_km_assessment": (build_qcto_km_assessment_docx_adapter, "docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
        "qcto_pm_assessment": (build_qcto_pm_assessment_docx_adapter, "docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
    "qcto_km_facilitator_guide": (build_qcto_km_facilitator_guide_docx_adapter, "docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
    "qcto_km_assessment_guide": (build_qcto_km_assessment_guide_docx_adapter, "docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
    "qcto_km_poe": (build_qcto_km_poe_docx_adapter, "docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
    "qcto_km_learner_workbook": (build_qcto_km_learner_workbook_docx_adapter, "docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
    "qcto_isa": (build_qcto_isa_docx_adapter, "docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
    "qcto_pm_facilitator_guide": (build_qcto_pm_facilitator_guide_docx_adapter, "docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
    "qcto_pm_assessment_guide": (build_qcto_pm_assessment_guide_docx_adapter, "docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
    "qcto_pm_poe": (build_qcto_pm_poe_docx_adapter, "docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
    "qcto_wm_supervisor_guide": (build_qcto_wm_supervisor_guide_docx_adapter, "docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
    "qcto_final_exam": (build_qcto_final_exam_docx_adapter, "docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
    "qcto_fisa": (build_qcto_fisa_docx_adapter, "docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
    "qcto_learning_matrix": (build_qcto_learning_matrix_docx_adapter, "docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
    "qcto_km_powerpoint": (build_qcto_km_powerpoint_zip_adapter, "zip", "application/zip"),
    "qcto_pm_powerpoint": (build_qcto_pm_powerpoint_zip_adapter, "zip", "application/zip"),
}

def _get_or_generate_km_assessment_content(syllabus, module, job_id=None):
    """Returns cached formative-assessment content for a KM module if already generated
    and persisted on the syllabus; otherwise generates it once via
    generate_qcto_assessment_content, persists it onto the module dict within the syllabus's
    content, commits, and returns it — so every subsequent caller (the KM Formative
    Assessment document AND the KM Facilitator Guide's Marking Memorandum) reads the exact
    same real questions, rather than each independently generating its own."""
    from app.services.ai_service import generate_qcto_assessment_content

    cached = module.get("generated_formative_assessment")
    if cached:
        return cached

    content = generate_qcto_assessment_content(module, job_id=job_id)
    module["generated_formative_assessment"] = content

    # Fresh reassignment — plain db.JSON columns don't auto-detect in-place mutation of
    # nested dicts/lists, so this forces SQLAlchemy to recognize the change on commit.
    modules = syllabus.content.get("modules", [])
    syllabus.content = {**syllabus.content, "modules": modules}
    db.session.commit()
    return content

def _get_or_generate_pm_scenario_groups(syllabus, module, job_id=None):
    """Returns cached PM scenario/questions groups for a PM module if already generated
    and persisted on the syllabus; otherwise generates them once (in parallel across
    groups) via generate_pm_scenario_and_questions, persists them, commits, and returns
    them — so PM Assessment Guide and PM POE, which both need this same content for the
    same modules, read identical scenarios instead of each independently generating its
    own, different, inconsistent version."""
    from app.services.ai_service import generate_pm_scenario_and_questions, parallel_map

    cached = module.get("generated_pm_scenario_groups")
    if cached:
        return cached

    pa_items = module.get("performance_assessment") or []
    group_size = 4
    groups = [pa_items[i:i + group_size] for i in range(0, len(pa_items), group_size)]

    results = parallel_map(
        groups,
        lambda g: generate_pm_scenario_and_questions(module.get("title", ""), g, job_id=job_id),
        max_workers=3,
    )

    module["generated_pm_scenario_groups"] = results
    modules = syllabus.content.get("modules", [])
    syllabus.content = {**syllabus.content, "modules": modules}
    db.session.commit()
    return results


def _get_or_generate_km_module_content(syllabus, module, job_id=None):
    """Returns cached full generated content for a KM module if already generated and
    persisted on the syllabus; otherwise generates it once, persists it, commits, and
    returns it — so the KM Learner Guide and the Learning Matrix (which needs this same
    content just to estimate page counts) don't each pay for their own independent AI
    generation of the same module's content."""
    from app.services.ai_service import generate_qcto_knowledge_module_content

    cached = module.get("generated_km_content")
    if cached:
        return cached

    content = generate_qcto_knowledge_module_content(module, job_id=job_id)
    module["generated_km_content"] = content
    modules = syllabus.content.get("modules", [])
    syllabus.content = {**syllabus.content, "modules": modules}
    db.session.commit()
    return content


def _get_or_generate_pm_module_content(syllabus, module, job_id=None):
    """Same caching pattern as _get_or_generate_km_module_content, for PM modules —
    shared between the PM Learner Guide and the Learning Matrix."""
    from app.services.ai_service import generate_qcto_practical_module_content

    cached = module.get("generated_pm_content")
    if cached:
        return cached

    content = generate_qcto_practical_module_content(module, job_id=job_id)
    module["generated_pm_content"] = content
    modules = syllabus.content.get("modules", [])
    syllabus.content = {**syllabus.content, "modules": modules}
    db.session.commit()
    return content


def _get_or_generate_wm_module_content(syllabus, module, job_id=None):
    """Same caching pattern, for WM modules — shared between the WM Guide and the
    Learning Matrix."""
    from app.services.ai_service import generate_qcto_workplace_module_content

    cached = module.get("generated_wm_content")
    if cached:
        return cached

    content = generate_qcto_workplace_module_content(module, job_id=job_id)
    module["generated_wm_content"] = content
    modules = syllabus.content.get("modules", [])
    syllabus.content = {**syllabus.content, "modules": modules}
    db.session.commit()
    return content

def _get_or_generate_textbook_chapter(syllabus, unit, title, seta=None, nqf_level=None, job_id=None):
    """Same caching pattern as the QCTO module helpers, applied to standard (non-QCTO)
    textbook chapters — cached on the unit dict within syllabus.content["units"] instead
    of syllabus.content["modules"], since standard syllabi use a different structure."""
    from app.services.ai_service import write_chapter_content

    cached = unit.get("generated_chapter_content")
    if cached:
        return cached

    content = write_chapter_content(unit.get("name", ""), unit.get("outcomes", []), course_title=title, seta=seta, nqf_level=nqf_level, job_id=job_id)
    unit["generated_chapter_content"] = content

    units = syllabus.content.get("units", [])
    syllabus.content = {**syllabus.content, "units": units}
    db.session.commit()
    return content


def _get_or_generate_presentation_slides(syllabus, unit, title, seta=None, nqf_level=None, job_id=None):
    """Same caching pattern, for presentation slide content per unit."""
    from app.services.ai_service import generate_slide_content

    cached = unit.get("generated_slide_content")
    if cached:
        return cached

    content = generate_slide_content(unit.get("name", ""), unit.get("outcomes", []), course_title=title, seta=seta, nqf_level=nqf_level, job_id=job_id)
    unit["generated_slide_content"] = content

    units = syllabus.content.get("units", [])
    syllabus.content = {**syllabus.content, "units": units}
    db.session.commit()
    return content

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
        if syllabus.syllabus_type == "qcto":
            units = syllabus.content.get("modules", [])
        else:
            units = syllabus.content.get("units", [])
        accreditation = syllabus.accreditation_info or {}

        # Every per-module/per-unit caching call below is individually wrapped in
        # try/except — a module or unit that fails (e.g. the whole AI provider chain
        # temporarily exhausted) is skipped rather than crashing the entire loop, so
        # everything before and after it still gets generated and cached this pass.
        # Since each successful item is already persisted to the database the moment
        # it's generated, a failed one simply isn't cached — meaning a retry of this
        # same job will find every already-succeeded item instantly (no re-generation)
        # and only need to re-attempt the one(s) that failed, rather than starting over
        # from scratch.
        if syllabus.syllabus_type == "qcto" and subtype in ("qcto_km_assessment", "qcto_km_facilitator_guide"):
            for module in units:
                if module.get("module_type") == "KM":
                    try:
                        _get_or_generate_km_assessment_content(syllabus, module, job_id=job.id)
                    except Exception as module_exc:
                        print(f"[RESUME] {module.get('module_code', '')} KM assessment content failed, will retry later: {module_exc}")
                        continue

        if syllabus.syllabus_type == "qcto" and subtype in ("qcto_pm_assessment_guide", "qcto_pm_poe"):
            for module in units:
                if module.get("module_type") == "PM":
                    try:
                        _get_or_generate_pm_scenario_groups(syllabus, module, job_id=job.id)
                    except Exception as module_exc:
                        print(f"[RESUME] {module.get('module_code', '')} PM scenario groups failed, will retry later: {module_exc}")
                        continue

        if syllabus.syllabus_type == "qcto" and subtype in ("qcto_knowledge_modules", "qcto_learning_matrix"):
            for module in units:
                if module.get("module_type") == "KM":
                    try:
                        _get_or_generate_km_module_content(syllabus, module, job_id=job.id)
                    except Exception as module_exc:
                        print(f"[RESUME] {module.get('module_code', '')} KM module content failed, will retry later: {module_exc}")
                        continue

        if syllabus.syllabus_type == "qcto" and subtype in ("qcto_practical_modules", "qcto_learning_matrix"):
            for module in units:
                if module.get("module_type") == "PM":
                    try:
                        _get_or_generate_pm_module_content(syllabus, module, job_id=job.id)
                    except Exception as module_exc:
                        print(f"[RESUME] {module.get('module_code', '')} PM module content failed, will retry later: {module_exc}")
                        continue

        if syllabus.syllabus_type == "qcto" and subtype in ("qcto_workplace_modules", "qcto_learning_matrix"):
            for module in units:
                if module.get("module_type") == "WM":
                    try:
                        _get_or_generate_wm_module_content(syllabus, module, job_id=job.id)
                    except Exception as module_exc:
                        print(f"[RESUME] {module.get('module_code', '')} WM module content failed, will retry later: {module_exc}")
                        continue

        if subtype == "textbook":
            for unit in units:
                try:
                    _get_or_generate_textbook_chapter(syllabus, unit, syllabus.title, seta=accreditation.get("seta"), nqf_level=accreditation.get("nqf_level"), job_id=job.id)
                except Exception as unit_exc:
                    print(f"[RESUME] {unit.get('name', '')} textbook chapter failed, will retry later: {unit_exc}")
                    continue

        if subtype == "presentation":
            for unit in units:
                try:
                    _get_or_generate_presentation_slides(syllabus, unit, syllabus.title, seta=accreditation.get("seta"), nqf_level=accreditation.get("nqf_level"), job_id=job.id)
                except Exception as unit_exc:
                    print(f"[RESUME] {unit.get('name', '')} presentation slides failed, will retry later: {unit_exc}")
                    continue

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
            accreditation_info=accreditation,
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
        db.session.expire_all()
        fresh_job = GenerationJob.query.get(job.id)
        if fresh_job and fresh_job.status == "cancelled":
            # Already marked cancelled by the user's Cancel button — don't overwrite
            # with "failed". The task stopped because of _JobCancelledError bubbling up
            # from ai_service.py, not a genuine error.
            return
        job.status = "failed"
        job.error_message = str(exc)
        db.session.commit()