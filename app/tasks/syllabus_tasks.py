"""Background tasks for syllabus processing — specifically QCTO extraction, which can
involve many sequential AI calls and shouldn't block the web request."""
from app.extensions import celery_app, db
from app.models.syllabus import Syllabus


@celery_app.task(name="process_qcto_syllabus_task")
def process_qcto_syllabus_task(syllabus_id: str, raw_text: str):
    from app.services.ai_service import (
        structure_qcto_syllabus_from_text, extract_qcto_module_topics,
        extract_qcto_pm_details, extract_qcto_wm_details,
    )

    syllabus = Syllabus.query.get(syllabus_id)
    if not syllabus:
        return

    try:
        content = structure_qcto_syllabus_from_text(raw_text)

        for module in content.get("modules", []):
            db.session.expire_all()
            fresh = Syllabus.query.get(syllabus_id)
            if fresh is None or fresh.status == "cancelled":
                # Cancellation was requested — stop processing further modules and leave
                # the status as "cancelled" rather than overwriting it with "draft"/"failed".
                return

            if module.get("module_type") == "KM" and not module.get("topics"):
                module["topics"] = extract_qcto_module_topics(
                    module.get("module_code", ""), module.get("title", ""), raw_text
                )
            elif module.get("module_type") == "PM" and not module.get("performance_assessment"):
                pm_detail = extract_qcto_pm_details(
                    module.get("module_code", ""), module.get("title", ""), raw_text
                )
                module["performance_assessment"] = pm_detail.get("performance_assessment", [])
                module["applied_knowledge"] = pm_detail.get("applied_knowledge", [])
                module["assessment_criteria"] = pm_detail.get("assessment_criteria", [])
            elif module.get("module_type") == "WM" and not module.get("work_experience_elements"):
                wm_detail = extract_qcto_wm_details(
                    module.get("module_code", ""), module.get("title", ""), raw_text
                )
                module["purpose"] = wm_detail.get("purpose") or module.get("purpose", "")
                module["work_experience_elements"] = wm_detail.get("work_experience_elements", [])

                db.session.expire_all()
        fresh = Syllabus.query.get(syllabus_id)
        if fresh is not None and fresh.status == "cancelled":
            return

        syllabus.content = content
        syllabus.accreditation_info = {
            **(syllabus.accreditation_info or {}),
            "qualification_code": content.get("qualification_code"),
            "qualification_title": content.get("qualification_title"),
        }
        syllabus.status = "draft"

        from app.models.review import Notification
        db.session.add(Notification(
            recipient_user_id=syllabus.created_by_user_id,
            message=f'Your QCTO curriculum "{syllabus.title}" has finished processing.',
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