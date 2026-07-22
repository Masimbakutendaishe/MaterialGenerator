"""Material generation page: pick a syllabus, trigger generation, poll status, download."""
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from app.extensions import db
from app.models.syllabus import Syllabus
from app.models.generation_job import GenerationJob
from app.models.review import MaterialReview
from app.tasks.generation_tasks import generate_textbook_task, generate_presentation_task
from app.services.storage_service import get_presigned_url

generation_web_bp = Blueprint("generation_web", __name__, url_prefix="/generate")


@generation_web_bp.route("/")
@login_required
def index():
    syllabi = Syllabus.query.filter_by(organization_id=current_user.organization_id).order_by(Syllabus.created_at.desc()).all()
    jobs = GenerationJob.query.filter_by(organization_id=current_user.organization_id).order_by(GenerationJob.created_at.desc()).limit(20).all()

    job_reviews = {}
    for job in jobs:
        review = MaterialReview.query.filter_by(generation_job_id=job.id).first()
        job_reviews[job.id] = review

    return render_template("generate/index.html", syllabi=syllabi, jobs=jobs, job_reviews=job_reviews)


@generation_web_bp.route("/trigger", methods=["POST"])
@login_required
def trigger():
    syllabus_id = request.form.get("syllabus_id")
    material_type = request.form.get("material_type")

    syllabus = Syllabus.query.filter_by(id=syllabus_id, organization_id=current_user.organization_id).first()
    if not syllabus:
        flash("Syllabus not found.")
        return redirect(url_for("generation_web.index"))

    job = GenerationJob(
        organization_id=current_user.organization_id,
        syllabus_id=syllabus_id,
        material_type=material_type,
    )
    db.session.add(job)
    db.session.commit()

    if material_type == "textbook":
        generate_textbook_task.delay(job.id)
    else:
        generate_presentation_task.delay(job.id)

    flash(f"Generating {material_type} for '{syllabus.title}'...")
    return redirect(url_for("generation_web.index"))


@generation_web_bp.route("/status/<job_id>")
@login_required
def status(job_id):
    """Polled by the page's JS to update job status live."""
    db.session.expire_all()
    job = GenerationJob.query.filter_by(id=job_id, organization_id=current_user.organization_id).first()
    if not job:
        return jsonify({"error": "not found"}), 404
    return jsonify({"job_id": job.id, "status": job.status, "error_message": job.error_message})


@generation_web_bp.route("/download/<job_id>")
@login_required
def download(job_id):
    job = GenerationJob.query.filter_by(id=job_id, organization_id=current_user.organization_id).first()
    if not job or job.status != "done":
        flash("Material is not ready to download.")
        return redirect(url_for("generation_web.index"))

    review = MaterialReview.query.filter_by(generation_job_id=job_id).first()
    if review and review.status != "approved":
        flash(f"This material is awaiting review (status: {review.status}).")
        return redirect(url_for("generation_web.index"))

    url = get_presigned_url(job.result_file_path, expires_in=300)
    return redirect(url)


@generation_web_bp.route("/submit-review/<job_id>", methods=["POST"])
@login_required
def submit_review(job_id):
    job = GenerationJob.query.filter_by(id=job_id, organization_id=current_user.organization_id).first()
    if not job or job.status != "done":
        flash("Material is not ready to submit for review.")
        return redirect(url_for("generation_web.index"))

    if MaterialReview.query.filter_by(generation_job_id=job_id).first():
        flash("This material was already submitted for review.")
        return redirect(url_for("generation_web.index"))

    if not current_user.reports_to_user_id:
        flash("You have no assigned QA reviewer. Ask your admin to set one.")
        return redirect(url_for("generation_web.index"))

    from app.models.review import Notification
    review = MaterialReview(
        generation_job_id=job_id,
        organization_id=current_user.organization_id,
        submitted_by_user_id=current_user.id,
        reviewer_user_id=current_user.reports_to_user_id,
        status="pending_review",
    )
    db.session.add(review)
    db.session.flush()
    db.session.add(Notification(
        recipient_user_id=current_user.reports_to_user_id,
        message=f"{current_user.email} submitted a {job.material_type} for your review.",
        link_review_id=review.id,
    ))
    db.session.commit()

    flash("Submitted for review.")
    return redirect(url_for("generation_web.index"))