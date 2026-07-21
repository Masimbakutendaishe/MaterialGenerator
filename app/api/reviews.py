"""Review workflow endpoints: submit for review, list pending, comment, approve/request changes."""
from flask import Blueprint, request, jsonify
from flask_jwt_extended import get_jwt, get_jwt_identity
from app.extensions import db
from app.utils.security import active_account_required
from app.models.generation_job import GenerationJob
from app.models.user import User
from app.models.review import MaterialReview, ReviewComment, Notification

reviews_bp = Blueprint("reviews", __name__)


@reviews_bp.route("/submit/<job_id>", methods=["POST"])
@active_account_required
def submit_for_review(job_id):
    """Submits a completed generation job for QA review. Requires the submitting user
    to have a reports_to_user_id set (their assigned QA reviewer)."""
    claims = get_jwt()
    org_id = claims.get("organization_id")
    user_id = get_jwt_identity()

    job = GenerationJob.query.filter_by(id=job_id, organization_id=org_id).first()
    if not job:
        return jsonify({"error": "Job not found"}), 404
    if job.status != "done":
        return jsonify({"error": f"Job is not ready to submit (status: {job.status})"}), 409

    existing = MaterialReview.query.filter_by(generation_job_id=job_id).first()
    if existing:
        return jsonify({"error": "This job has already been submitted for review", "review_id": existing.id}), 409

    submitter = User.query.get(user_id)
    if not submitter.reports_to_user_id:
        return jsonify({"error": "You have no assigned QA reviewer. Ask your admin to set one."}), 400

    review = MaterialReview(
        generation_job_id=job_id,
        organization_id=org_id,
        submitted_by_user_id=user_id,
        reviewer_user_id=submitter.reports_to_user_id,
        status="pending_review",
    )
    db.session.add(review)
    db.session.flush()

    notification = Notification(
        recipient_user_id=submitter.reports_to_user_id,
        message=f"{submitter.email} submitted a {job.material_type} for your review.",
        link_review_id=review.id,
    )
    db.session.add(notification)
    db.session.commit()

    return jsonify({"review_id": review.id, "status": review.status}), 201


@reviews_bp.route("/pending", methods=["GET"])
@active_account_required
def list_pending_reviews():
    """Lists reviews assigned to the current user (as reviewer) that need attention."""
    user_id = get_jwt_identity()
    reviews = MaterialReview.query.filter(
        MaterialReview.reviewer_user_id == user_id,
        MaterialReview.status != "approved"
    ).order_by(MaterialReview.created_at.desc()).all()

    return jsonify([{
        "review_id": r.id,
        "generation_job_id": r.generation_job_id,
        "status": r.status,
        "submitted_by_user_id": r.submitted_by_user_id,
        "created_at": r.created_at.isoformat(),
    } for r in reviews]), 200


@reviews_bp.route("/<review_id>", methods=["GET"])
@active_account_required
def get_review(review_id):
    """Full review detail including the comment thread. Accessible to the submitter or reviewer."""
    claims = get_jwt()
    org_id = claims.get("organization_id")
    user_id = get_jwt_identity()

    review = MaterialReview.query.filter_by(id=review_id, organization_id=org_id).first()
    if not review:
        return jsonify({"error": "Review not found"}), 404
    if user_id not in (review.submitted_by_user_id, review.reviewer_user_id):
        return jsonify({"error": "You do not have access to this review"}), 403

    return jsonify({
        "review_id": review.id,
        "generation_job_id": review.generation_job_id,
        "status": review.status,
        "submitted_by_user_id": review.submitted_by_user_id,
        "reviewer_user_id": review.reviewer_user_id,
        "comments": [{
            "id": c.id, "author_user_id": c.author_user_id, "body": c.body,
            "created_at": c.created_at.isoformat(),
        } for c in review.comments],
    }), 200


@reviews_bp.route("/<review_id>/comments", methods=["POST"])
@active_account_required
def add_comment(review_id):
    """Adds a comment to the review thread. Either party (submitter or reviewer) can comment."""
    claims = get_jwt()
    org_id = claims.get("organization_id")
    user_id = get_jwt_identity()

    review = MaterialReview.query.filter_by(id=review_id, organization_id=org_id).first()
    if not review:
        return jsonify({"error": "Review not found"}), 404
    if user_id not in (review.submitted_by_user_id, review.reviewer_user_id):
        return jsonify({"error": "You do not have access to this review"}), 403

    data = request.get_json() or {}
    body = data.get("body")
    if not body:
        return jsonify({"error": "body is required"}), 400

    comment = ReviewComment(review_id=review_id, author_user_id=user_id, body=body)
    db.session.add(comment)

    # Notify the other party
    recipient = review.reviewer_user_id if user_id == review.submitted_by_user_id else review.submitted_by_user_id
    notification = Notification(
        recipient_user_id=recipient,
        message="New comment on a material review.",
        link_review_id=review.id,
    )
    db.session.add(notification)
    db.session.commit()

    return jsonify({"id": comment.id, "body": comment.body, "created_at": comment.created_at.isoformat()}), 201


@reviews_bp.route("/<review_id>/decision", methods=["POST"])
@active_account_required
def submit_decision(review_id):
    """Reviewer approves or requests changes. Only the assigned reviewer can call this."""
    claims = get_jwt()
    org_id = claims.get("organization_id")
    user_id = get_jwt_identity()

    review = MaterialReview.query.filter_by(id=review_id, organization_id=org_id).first()
    if not review:
        return jsonify({"error": "Review not found"}), 404
    if user_id != review.reviewer_user_id:
        return jsonify({"error": "Only the assigned reviewer can decide on this review"}), 403

    data = request.get_json() or {}
    decision = data.get("decision")  # "approved" | "changes_requested"
    if decision not in ("approved", "changes_requested"):
        return jsonify({"error": "decision must be 'approved' or 'changes_requested'"}), 400

    review.status = decision
    db.session.add(review)

    notification = Notification(
        recipient_user_id=review.submitted_by_user_id,
        message=f"Your material was {'approved' if decision == 'approved' else 'sent back with requested changes'}.",
        link_review_id=review.id,
    )
    db.session.add(notification)
    db.session.commit()

    return jsonify({"review_id": review.id, "status": review.status}), 200


@reviews_bp.route("/notifications", methods=["GET"])
@active_account_required
def list_notifications():
    """Lists the current user's notifications, unread first."""
    user_id = get_jwt_identity()
    notifications = Notification.query.filter_by(recipient_user_id=user_id).order_by(
        Notification.is_read.asc(), Notification.created_at.desc()
    ).all()

    return jsonify([{
        "id": n.id, "message": n.message, "is_read": n.is_read,
        "link_review_id": n.link_review_id, "created_at": n.created_at.isoformat(),
    } for n in notifications]), 200


@reviews_bp.route("/notifications/<notification_id>/read", methods=["POST"])
@active_account_required
def mark_notification_read(notification_id):
    user_id = get_jwt_identity()
    notification = Notification.query.filter_by(id=notification_id, recipient_user_id=user_id).first()
    if not notification:
        return jsonify({"error": "Notification not found"}), 404

    notification.is_read = True
    db.session.commit()
    return jsonify({"id": notification.id, "is_read": True}), 200