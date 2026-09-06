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
