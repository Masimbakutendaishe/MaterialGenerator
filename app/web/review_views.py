"""Review web pages: pending queue, detail with comment thread, decisions, notifications."""
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from app.extensions import db
from app.models.review import MaterialReview, ReviewComment, Notification
from app.models.generation_job import GenerationJob
from app.models.syllabus import Syllabus
from app.models.user import User

review_web_bp = Blueprint("review_web", __name__, url_prefix="/reviews")


# Order in which a QA reviewer expects to see a full set: KM, then PM, then WM, then programme level.
_DOC_ORDER = [
    "qcto_knowledge_modules", "qcto_km_facilitator_guide", "qcto_km_powerpoint", "qcto_video_guide",
    "qcto_km_learner_workbook", "qcto_km_poe", "qcto_km_poe_memo", "qcto_km_assessment",
    "qcto_km_assessment_memo", "qcto_km_assessment_guide",
    "qcto_practical_modules", "qcto_pm_facilitator_guide", "qcto_pm_powerpoint", "qcto_pm_poe",
    "qcto_pm_assessment", "qcto_pm_assessment_memo", "qcto_pm_assessment_guide",
    "qcto_workplace_modules", "qcto_wm_supervisor_guide", "qcto_workplace_logbook", "qcto_wm_statement_of_work",
    "qcto_isa", "qcto_final_exam", "qcto_fisa", "qcto_learning_matrix", "qcto_reference_documents",
]


def _doc_order(subtype):
    try:
        return _DOC_ORDER.index(subtype)
    except ValueError:
        return len(_DOC_ORDER)


def _download_name(subtype, title, stored_path):
    """Readable file name for the browser's Save dialog, e.g. 'KM Learner Guide - HS Practitioner.docx'.
    The stored object key is untouched; only the suggested download name changes."""
    import re
    from app.services.seta_constants import document_display_name
    ext = ""
    if stored_path and "." in stored_path.rsplit("/", 1)[-1]:
        ext = "." + stored_path.rsplit(".", 1)[-1].lower()
    label = document_display_name(subtype) or "Document"
    name = f"{label} - {title}" if title else label
    name = re.sub(r'[\\/:*?"<>|]+', "-", name).encode("ascii", "ignore").decode()
    name = re.sub(r"\s+", " ", name).strip(" .-")
    return (name or "Document") + ext

@review_web_bp.route("/")
@login_required
def list_reviews():
    """QA reviewers see what's assigned to them; workers see what they've submitted."""
    if current_user.role == "qa_reviewer":
        reviews = MaterialReview.query.filter_by(reviewer_user_id=current_user.id).order_by(MaterialReview.created_at.desc()).all()
    else:
        reviews = MaterialReview.query.filter_by(submitted_by_user_id=current_user.id).order_by(MaterialReview.created_at.desc()).all()

    from app.models.material_package import MaterialPackage

    enriched = []
    for r in reviews:
        if r.package_id:
            package = MaterialPackage.query.get(r.package_id)
            syllabus = Syllabus.query.get(package.syllabus_id) if package else None
            enriched.append({
                "review": r, "job": None,
                "syllabus_title": syllabus.title if syllabus else "Unknown",
                "material_type": package.package_type.replace("_", " ") if package else "package",
            })
        else:
            job = GenerationJob.query.get(r.generation_job_id)
            syllabus = Syllabus.query.get(job.syllabus_id) if job else None
            enriched.append({
                "review": r, "job": job,
                "syllabus_title": syllabus.title if syllabus else "Unknown",
                "material_type": job.material_type if job else "—",
            })

    return render_template("reviews/list.html", items=enriched)


@review_web_bp.route("/<review_id>")
@login_required
def review_detail(review_id):
    review = MaterialReview.query.filter_by(id=review_id, organization_id=current_user.organization_id).first_or_404()
    if current_user.id not in (review.submitted_by_user_id, review.reviewer_user_id):
        flash("You do not have access to that review.")
        return redirect(url_for("review_web.list_reviews"))

    submitter = User.query.get(review.submitted_by_user_id)
    reviewer = User.query.get(review.reviewer_user_id)

    Notification.query.filter_by(recipient_user_id=current_user.id, link_review_id=review_id, is_read=False).update({"is_read": True})
    db.session.commit()

    from app.services.storage_service import get_presigned_url

    # Enrich each comment with its author's name/initial/avatar, so the template
    # doesn't need to look anything up itself.
    enriched_comments = []
    for c in review.comments:
        author = User.query.get(c.author_user_id)
        avatar_url = get_presigned_url(author.profile_picture_url, expires_in=600) if author and author.profile_picture_url else None
        initial = (author.first_name[0] if author and author.first_name else (author.email[0] if author else "?")).upper()
        display_name = f"{author.first_name} {author.last_name}" if author and author.first_name else (author.email if author else "Unknown")
        enriched_comments.append({
            "comment": c,
            "author_id": c.author_user_id,
            "avatar_url": avatar_url,
            "initial": initial,
            "display_name": display_name,
        })

    if review.package_id:
        from app.models.material_package import MaterialPackage
        package = MaterialPackage.query.get(review.package_id)
        syllabus = Syllabus.query.get(package.syllabus_id) if package else None
        job = None
        material_url = None
        package_documents = []
        for j in (package.jobs if package else []):
            url = get_presigned_url(
                j.result_file_path, expires_in=600,
                download_filename=_download_name(j.document_subtype, syllabus.title if syllabus else "", j.result_file_path),
            ) if j.result_file_path else None
            package_documents.append({"job": j, "url": url})
        package_documents.sort(key=lambda d: _doc_order(d["job"].document_subtype))
    else:
        job = GenerationJob.query.get(review.generation_job_id)
        syllabus = Syllabus.query.get(job.syllabus_id) if job else None
        material_url = get_presigned_url(
            job.result_file_path, expires_in=600,
            download_filename=_download_name(getattr(job, "document_subtype", None) or job.material_type, syllabus.title if syllabus else "", job.result_file_path),
        ) if job and job.result_file_path else None
        package_documents = None

    return render_template(
        "reviews/detail.html",
        review=review, job=job, syllabus=syllabus, submitter=submitter, reviewer=reviewer,
        material_url=material_url, package_documents=package_documents, enriched_comments=enriched_comments,
    )


@review_web_bp.route("/<review_id>/comment", methods=["POST"])
@login_required
def add_comment(review_id):
    review = MaterialReview.query.filter_by(id=review_id, organization_id=current_user.organization_id).first_or_404()
    if current_user.id not in (review.submitted_by_user_id, review.reviewer_user_id):
        flash("You do not have access to that review.")
        return redirect(url_for("review_web.list_reviews"))

    body = request.form.get("body")
    if body and body.strip():
        comment = ReviewComment(review_id=review_id, author_user_id=current_user.id, body=body.strip())
        db.session.add(comment)

        recipient = review.reviewer_user_id if current_user.id == review.submitted_by_user_id else review.submitted_by_user_id
        db.session.add(Notification(
            recipient_user_id=recipient,
            message="New comment on a material review.",
            link_review_id=review_id,
        ))
        db.session.commit()

    return redirect(url_for("review_web.review_detail", review_id=review_id))


@review_web_bp.route("/<review_id>/decision", methods=["POST"])
@login_required
def submit_decision(review_id):
    review = MaterialReview.query.filter_by(id=review_id, organization_id=current_user.organization_id).first_or_404()
    if current_user.id != review.reviewer_user_id:
        flash("Only the assigned reviewer can decide on this review.")
        return redirect(url_for("review_web.list_reviews"))

    decision = request.form.get("decision")
    if decision in ("approved", "changes_requested"):
        review.status = decision
        db.session.add(Notification(
            recipient_user_id=review.submitted_by_user_id,
            message=f"Your material was {'approved' if decision == 'approved' else 'sent back with requested changes'}.",
            link_review_id=review_id,
        ))
        db.session.commit()
        flash(f"Review marked as {decision.replace('_', ' ')}.")

    return redirect(url_for("review_web.review_detail", review_id=review_id))


@review_web_bp.route("/notifications/count")
@login_required
def notification_count():
    count = Notification.query.filter_by(recipient_user_id=current_user.id, is_read=False).count()
    return jsonify({"count": count})


@review_web_bp.route("/notifications/dropdown")
@login_required
def notifications_dropdown():
    notifications = Notification.query.filter_by(recipient_user_id=current_user.id).order_by(
        Notification.is_read.asc(), Notification.created_at.desc()
    ).limit(10).all()
    return render_template("reviews/_notification_dropdown.html", notifications=notifications)

@review_web_bp.route("/notifications/mark-all-read", methods=["POST"])
@login_required
def mark_all_read():
    Notification.query.filter_by(recipient_user_id=current_user.id, is_read=False).update({"is_read": True})
    db.session.commit()
    return jsonify({"status": "ok"})

@review_web_bp.route("/notifications/<notification_id>/read", methods=["POST"])
@login_required
def mark_notification_read(notification_id):
    notification = Notification.query.filter_by(id=notification_id, recipient_user_id=current_user.id).first()
    if notification:
        notification.is_read = True
        db.session.commit()
    return jsonify({"status": "ok"})