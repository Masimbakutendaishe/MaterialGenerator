"""Review web pages: pending queue, detail with comment thread, decisions, notifications."""
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from app.extensions import db
from app.models.review import MaterialReview, ReviewComment, Notification
from app.models.generation_job import GenerationJob
from app.models.syllabus import Syllabus
from app.models.user import User

review_web_bp = Blueprint("review_web", __name__, url_prefix="/reviews")


@review_web_bp.route("/")
@login_required
def list_reviews():
    """QA reviewers see what's assigned to them; workers see what they've submitted."""
    if current_user.role == "qa_reviewer":
        reviews = MaterialReview.query.filter_by(reviewer_user_id=current_user.id).order_by(MaterialReview.created_at.desc()).all()
    else:
        reviews = MaterialReview.query.filter_by(submitted_by_user_id=current_user.id).order_by(MaterialReview.created_at.desc()).all()

    enriched = []
    for r in reviews:
        job = GenerationJob.query.get(r.generation_job_id)
        syllabus = Syllabus.query.get(job.syllabus_id) if job else None
        enriched.append({"review": r, "job": job, "syllabus_title": syllabus.title if syllabus else "Unknown"})

    return render_template("reviews/list.html", items=enriched)


@review_web_bp.route("/<review_id>")
@login_required
def review_detail(review_id):
    review = MaterialReview.query.filter_by(id=review_id, organization_id=current_user.organization_id).first_or_404()
    if current_user.id not in (review.submitted_by_user_id, review.reviewer_user_id):
        flash("You do not have access to that review.")
        return redirect(url_for("review_web.list_reviews"))

    job = GenerationJob.query.get(review.generation_job_id)
    syllabus = Syllabus.query.get(job.syllabus_id) if job else None
    submitter = User.query.get(review.submitted_by_user_id)
    reviewer = User.query.get(review.reviewer_user_id)

    Notification.query.filter_by(recipient_user_id=current_user.id, link_review_id=review_id, is_read=False).update({"is_read": True})
    db.session.commit()

    from app.services.storage_service import get_presigned_url
    material_url = get_presigned_url(job.result_file_path, expires_in=600) if job and job.result_file_path else None

    return render_template(
        "reviews/detail.html",
        review=review, job=job, syllabus=syllabus, submitter=submitter, reviewer=reviewer, material_url=material_url,
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