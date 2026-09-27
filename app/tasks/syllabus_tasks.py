"""Background tasks for syllabus processing — specifically QCTO extraction, which can
involve many sequential AI calls and shouldn't block the web request."""
from app.extensions import celery_app, db
from app.models.syllabus import Syllabus


def _extract_module_detail(module: dict, raw_text: str) -> dict:
    """Dispatches to the right second-pass extraction function based on module type and
    returns the result — does NOT mutate the module dict directly, since this runs inside
    a parallel worker thread; the caller applies the result back onto the module after the
    parallel batch completes, keeping all shared-state mutation on the main thread."""
    from app.services.ai_service import extract_qcto_module_topics, extract_qcto_pm_details, extract_qcto_wm_details

    module_type = module.get("module_type")
    module_code = module.get("module_code", "")
    module_title = module.get("title", "")

    if module_type == "KM":
        topics = extract_qcto_module_topics(module_code, module_title, raw_text)
        return {"topics": topics}
    elif module_type == "PM":
        pm_detail = extract_qcto_pm_details(module_code, module_title, raw_text)
        return {
            "performance_assessment": pm_detail.get("performance_assessment", []),
            "applied_knowledge": pm_detail.get("applied_knowledge", []),
            "guidelines": pm_detail.get("guidelines"),
            "assessment_criteria": pm_detail.get("assessment_criteria", []),
        }
    elif module_type == "WM":
        wm_detail = extract_qcto_wm_details(module_code, module_title, raw_text)
        return {
            "purpose": wm_detail.get("purpose") or module.get("purpose", ""),
            "work_experience_elements": wm_detail.get("work_experience_elements", []),
            "guidelines": wm_detail.get("guidelines"),
        }
    return {}

def _module_has_detail(module: dict) -> bool:
    """Checks whether a module already has genuine second-pass extraction detail,
    type-aware since KM/PM/WM each use different fields for this. A module with detail
    already present should never be re-extracted on retry — only genuinely failed ones."""
    module_type = module.get("module_type")
    if module_type == "KM":
        topics = module.get("topics", [])
        return any(t.get("elements") or t.get("assessment_criteria") for t in topics)
    elif module_type == "PM":
        return bool(module.get("performance_assessment") or module.get("assessment_criteria"))
    elif module_type == "WM":
        return bool(module.get("work_experience_elements"))
    return True  # unknown type — don't touch it


@celery_app.task(name="retry_qcto_extraction_task")
def retry_qcto_extraction_task(syllabus_id: str, raw_text: str):
    """Re-attempts second-pass module detail extraction only for modules that genuinely
    lack it (a prior failure) — modules that already succeeded are left completely
    untouched, so a retry after a transient AI provider issue looks exactly as if
    everything had succeeded the first time, rather than regenerating and potentially
    producing different content for modules that were already fine."""
    from app.services.ai_service import parallel_map

    syllabus = Syllabus.query.get(syllabus_id)
    if not syllabus:
        return

    try:
        modules = syllabus.content.get("modules", [])
        modules_to_retry = [m for m in modules if not _module_has_detail(m)]

        extraction_warnings = []
        batch_size = 3
        for batch_start in range(0, len(modules_to_retry), batch_size):
            db.session.expire_all()
            fresh = Syllabus.query.get(syllabus_id)
            if fresh is None or fresh.status == "cancelled":
                return

            batch = modules_to_retry[batch_start:batch_start + batch_size]
            results = parallel_map(batch, lambda m: _extract_module_detail(m, raw_text), max_workers=3)

            for module, result in zip(batch, results):
                if result is None:
                    extraction_warnings.append(f"{module.get('module_code', module.get('title', ''))}: extraction failed")
                    continue
                module.update(result)
                if not _module_has_detail(module):
                    extraction_warnings.append(f"{module.get('module_code', module.get('title', ''))}: extraction returned no usable detail")

        # Fresh reassignment — plain db.JSON columns don't auto-detect in-place mutation
        # of nested dicts/lists, so this forces SQLAlchemy to recognize the change.
        syllabus.content = {**syllabus.content, "modules": modules}
        if extraction_warnings:
            syllabus.content["extraction_warnings"] = extraction_warnings
        elif "extraction_warnings" in syllabus.content:
            syllabus.content = {k: v for k, v in syllabus.content.items() if k != "extraction_warnings"}
        syllabus.status = "draft"

        from app.models.review import Notification
        notification_message = f'Retry finished for "{syllabus.title}" — {len(modules_to_retry) - len(extraction_warnings)} of {len(modules_to_retry)} previously-failed module(s) now have full detail.'
        db.session.add(Notification(
            recipient_user_id=syllabus.created_by_user_id,
            message=notification_message,
        ))
        db.session.commit()
    except Exception as exc:
        db.session.add(Notification(
            recipient_user_id=syllabus.created_by_user_id,
            message=f'Retry failed for "{syllabus.title}": {exc}',
        ))
        db.session.commit()


@celery_app.task(name="process_qcto_syllabus_task")
def process_qcto_syllabus_task(syllabus_id: str, raw_text: str):
    from app.services.ai_service import structure_qcto_syllabus_from_text, parallel_map

    syllabus = Syllabus.query.get(syllabus_id)
    if not syllabus:
        return

    try:
        content = structure_qcto_syllabus_from_text(raw_text)
        extraction_warnings = []
        modules = content.get("modules", [])

        # Process modules in batches of 3, running each batch's AI calls concurrently —
        # for a curriculum with many modules (this app has seen 30+), the old fully
        # sequential loop was the dominant cost in processing time. Cancellation is now
        # checked once per batch rather than once per module — a deliberate trade of
        # slightly coarser cancellation granularity (stops within ~3 modules' worth of
        # time instead of 1) for a roughly 3x reduction in overall processing time.
        batch_size = 3
        for batch_start in range(0, len(modules), batch_size):
            db.session.expire_all()
            fresh = Syllabus.query.get(syllabus_id)
            if fresh is None or fresh.status == "cancelled":
                # Cancellation was requested — stop processing further batches and leave
                # the status as "cancelled" rather than overwriting it with "draft"/"failed".
                return

            batch = modules[batch_start:batch_start + batch_size]
            results = parallel_map(batch, lambda m: _extract_module_detail(m, raw_text), max_workers=3)

            for module, result in zip(batch, results):
                if result is None:
                    extraction_warnings.append(f"{module.get('module_code', module.get('title', ''))}: extraction failed")
                    continue
                module.update(result)
                if not _module_has_detail(module):
                    extraction_warnings.append(f"{module.get('module_code', module.get('title', ''))}: extraction returned no usable detail")

        db.session.expire_all()
        fresh = Syllabus.query.get(syllabus_id)
        if fresh is not None and fresh.status == "cancelled":
            return

        syllabus.content = content
        if extraction_warnings:
            syllabus.content["extraction_warnings"] = extraction_warnings
        syllabus.accreditation_info = {
            **(syllabus.accreditation_info or {}),
            "qualification_code": content.get("qualification_code"),
            "qualification_title": content.get("qualification_title"),
        }
        syllabus.status = "draft"

        from app.models.review import Notification
        notification_message = f'Your QCTO curriculum "{syllabus.title}" has finished processing.'
        if extraction_warnings:
            notification_message += f" {len(extraction_warnings)} module(s) had incomplete detail extraction — check the curriculum for gaps."
        db.session.add(Notification(
            recipient_user_id=syllabus.created_by_user_id,
            message=notification_message,
        ))
        db.session.commit()

    except Exception as exc:
        syllabus.status = "failed"
        syllabus.content = {"error": str(exc)}
        db.session.commit()

@celery_app.task(name="process_standard_syllabus_task")
def process_standard_syllabus_task(syllabus_id: str, raw_text: str, seta: str = None, nqf_level: str = None):
    from app.services.ai_service import structure_syllabus_from_text

    syllabus = Syllabus.query.get(syllabus_id)
    if not syllabus:
        return

    try:
        content = structure_syllabus_from_text(raw_text, seta=seta, nqf_level=nqf_level)

        db.session.expire_all()
        fresh = Syllabus.query.get(syllabus_id)
        if fresh is not None and fresh.status == "cancelled":
            return

        syllabus.content = content
        syllabus.status = "draft"

        from app.models.review import Notification
        db.session.add(Notification(
            recipient_user_id=syllabus.created_by_user_id,
            message=f'Your syllabus "{syllabus.title}" has finished processing.',
        ))
        db.session.commit()
    except Exception as exc:
        syllabus.status = "failed"
        syllabus.content = {"error": str(exc)}
        db.session.commit()

@celery_app.task(name="process_eas_upload_task")
def process_eas_upload_task(syllabus_id: str, raw_text: str):
    """Extracts Exit Level Outcomes from an uploaded External Assessment Specification
    document and stores them on the syllabus's content, alongside its modules."""
    from app.services.ai_service import extract_exit_level_outcomes

    syllabus = Syllabus.query.get(syllabus_id)
    if not syllabus:
        return

    try:
        exit_level_outcomes = extract_exit_level_outcomes(raw_text)
        syllabus.content = {**syllabus.content, "exit_level_outcomes": exit_level_outcomes}

        from app.models.review import Notification
        db.session.add(Notification(
            recipient_user_id=syllabus.created_by_user_id,
            message=f'The External Assessment Specification for "{syllabus.title}" has finished processing.',
        ))
        db.session.commit()
    except Exception as exc:
        db.session.add(Notification(
            recipient_user_id=syllabus.created_by_user_id,
            message=f'Processing the External Assessment Specification for "{syllabus.title}" failed: {exc}',
        ))
        db.session.commit()



@celery_app.task(name="process_ai_generate_syllabus_task")
def process_ai_generate_syllabus_task(syllabus_id: str, topic: str, seta: str = None, nqf_level: str = None):
    from app.services.ai_service import generate_syllabus

    syllabus = Syllabus.query.get(syllabus_id)
    if not syllabus:
        return

    try:
        content = generate_syllabus(topic, seta=seta, nqf_level=nqf_level)
        syllabus.content = content
        syllabus.status = "draft"

        from app.models.review import Notification
        db.session.add(Notification(
            recipient_user_id=syllabus.created_by_user_id,
            message=f'Your syllabus "{syllabus.title}" has finished generating.',
        ))
        db.session.commit()

    except Exception as exc:
        syllabus.status = "failed"
        syllabus.content = {"error": str(exc)}
        db.session.commit()
