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



@generation_web_bp.route("/trigger", methods=["POST"])
@login_required
def trigger():
    from app.tasks.generation_tasks import generate_package_document_task, DOCUMENT_BUILDERS

    syllabus_id = request.form.get("syllabus_id")
    material_type = request.form.get("material_type")

    syllabus = Syllabus.query.filter_by(id=syllabus_id, organization_id=current_user.organization_id).first()
    if not syllabus:
        flash("Syllabus not found.")
        return redirect(url_for("generation_web.index"))

    if material_type not in DOCUMENT_BUILDERS:
        flash("Invalid document type.")
        return redirect(url_for("generation_web.index"))

    is_qcto_type = material_type.startswith("qcto_")
    is_qcto_syllabus = syllabus.syllabus_type == "qcto"
    if is_qcto_type != is_qcto_syllabus:
        flash("This document type requires a matching syllabus (occupational qualification documents need an occupational qualification syllabus, and vice versa).")
        return redirect(url_for("generation_web.index"))

    job = GenerationJob(
        organization_id=current_user.organization_id,
        syllabus_id=syllabus_id,
        material_type=material_type,
        document_subtype=material_type,
        triggered_by_user_id=current_user.id,
    )
    db.session.add(job)
    db.session.commit()

    async_result = generate_package_document_task.delay(job.id)
    job.task_id = async_result.id
    db.session.commit()

    flash(f"Generating {material_type.replace('_', ' ')} for '{syllabus.title}'...")
    return redirect(url_for("generation_web.index"))


@generation_web_bp.route("/cancel/<job_id>", methods=["POST"])
@login_required
def cancel(job_id):
    from app.extensions import celery_app

    job = GenerationJob.query.filter_by(id=job_id, organization_id=current_user.organization_id).first()
    if not job:
        flash("Job not found.")
        return redirect(request.referrer or url_for("generation_web.index"))

    if job.status in ("done", "failed", "cancelled"):
        flash("This job can no longer be cancelled.")
        return redirect(request.referrer or url_for("generation_web.index"))

    if job.task_id:
        celery_app.control.revoke(job.task_id, terminate=True)

    job.status = "cancelled"
    db.session.commit()

    flash("Generation cancelled.")
    return redirect(request.referrer or url_for("generation_web.index"))


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

@generation_web_bp.route("/row/<job_id>")
@login_required
def row_partial(job_id):
    """Renders a single job row — used for in-place status updates without a full page reload."""
    job = GenerationJob.query.filter_by(id=job_id, organization_id=current_user.organization_id).first_or_404()
    syllabus = Syllabus.query.get(job.syllabus_id)
    review = MaterialReview.query.filter_by(generation_job_id=job.id).first()
    return render_template(
        "generate/_job_row.html",
        job=job,
        syllabus_title=syllabus.title if syllabus else "Unknown",
        review=review,
    )


@generation_web_bp.route("/trigger-package", methods=["POST"])
@login_required
def trigger_package():
    from app.models.material_package import MaterialPackage, PACKAGE_DOCUMENTS
    from app.tasks.generation_tasks import generate_package_document_task

    syllabus_id = request.form.get("syllabus_id")
    package_type = request.form.get("package_type")

    syllabus = Syllabus.query.filter_by(id=syllabus_id, organization_id=current_user.organization_id).first()
    if not syllabus:
        flash("Syllabus not found.")
        return redirect(url_for("generation_web.index"))

    if package_type not in PACKAGE_DOCUMENTS:
        flash("Invalid package type.")
        return redirect(url_for("generation_web.index"))

    package = MaterialPackage(
        organization_id=current_user.organization_id,
        syllabus_id=syllabus_id,
        triggered_by_user_id=current_user.id,
        package_type=package_type,
    )
    db.session.add(package)
    db.session.flush()

    for subtype in PACKAGE_DOCUMENTS[package_type]:
        job = GenerationJob(
            organization_id=current_user.organization_id,
            syllabus_id=syllabus_id,
            material_type=subtype,
            document_subtype=subtype,
            package_id=package.id,
            triggered_by_user_id=current_user.id,
        )
        db.session.add(job)
        db.session.flush()
        async_result = generate_package_document_task.delay(job.id)
        job.task_id = async_result.id

    db.session.commit()

    flash(f"Generating {package_type.replace('_', ' ')} for '{syllabus.title}'...")
    return redirect(url_for("generation_web.index"))


@generation_web_bp.route("/submit-package-review/<package_id>", methods=["POST"])
@login_required
def submit_package_review(package_id):
    from app.models.material_package import MaterialPackage
    from app.models.review import MaterialReview, Notification, prune_old_notifications

    package = MaterialPackage.query.filter_by(id=package_id, organization_id=current_user.organization_id).first()
    if not package or package.status != "done":
        flash("Package is not ready to submit for review.")
        return redirect(url_for("generation_web.index"))

    if MaterialReview.query.filter_by(package_id=package_id).first():
        flash("This package was already submitted for review.")
        return redirect(url_for("generation_web.index"))

    if not current_user.reports_to_user_id:
        flash("You have no assigned QA reviewer. Ask your admin to set one.")
        return redirect(url_for("generation_web.index"))

    review = MaterialReview(
        package_id=package_id,
        organization_id=current_user.organization_id,
        submitted_by_user_id=current_user.id,
        reviewer_user_id=current_user.reports_to_user_id,
        status="pending_review",
    )
    db.session.add(review)
    db.session.flush()

    db.session.add(Notification(
        recipient_user_id=current_user.reports_to_user_id,
        message=f"{current_user.email} submitted a {package.package_type.replace('_', ' ')} for your review.",
        link_review_id=review.id,
    ))
    prune_old_notifications(current_user.reports_to_user_id)
    db.session.commit()

    flash("Package submitted for review.")
    return redirect(url_for("generation_web.index"))


@generation_web_bp.route("/package/<package_id>")
@login_required
def package_detail(package_id):
    from app.models.material_package import MaterialPackage

    package = MaterialPackage.query.filter_by(id=package_id, organization_id=current_user.organization_id).first_or_404()
    syllabus = Syllabus.query.get(package.syllabus_id)
    review = MaterialReview.query.filter_by(package_id=package_id).first()

    can_download = not review or review.status == "approved"

    return render_template("generate/package_detail.html", package=package, syllabus=syllabus, review=review, can_download=can_download)


@generation_web_bp.route("/package-status/<package_id>")
@login_required
def package_status(package_id):
    from app.models.material_package import MaterialPackage
    db.session.expire_all()
    package = MaterialPackage.query.filter_by(id=package_id, organization_id=current_user.organization_id).first()
    if not package:
        return jsonify({"error": "not found"}), 404
    return jsonify({"package_id": package.id, "status": package.status})


@generation_web_bp.route("/package-row/<package_id>")
@login_required
def package_row_partial(package_id):
    from app.models.material_package import MaterialPackage
    package = MaterialPackage.query.filter_by(id=package_id, organization_id=current_user.organization_id).first_or_404()
    syllabus = Syllabus.query.get(package.syllabus_id)
    review = MaterialReview.query.filter_by(package_id=package.id).first()
    return render_template(
        "generate/_package_row.html",
        item={"package": package, "title": syllabus.title if syllabus else "Unknown", "review": review},
    )

@generation_web_bp.route("/package/<package_id>/cancel-all", methods=["POST"])
@login_required
def cancel_package(package_id):
    from app.models.material_package import MaterialPackage
    from app.extensions import celery_app

    package = MaterialPackage.query.filter_by(id=package_id, organization_id=current_user.organization_id).first()
    if not package:
        flash("Package not found.")
        return redirect(url_for("generation_web.index"))

    cancelled_count = 0
    for job in package.jobs:
        if job.status in ("queued", "running"):
            if job.task_id:
                celery_app.control.revoke(job.task_id, terminate=True)
            job.status = "cancelled"
            cancelled_count += 1

    db.session.commit()
    flash(f"Cancelled {cancelled_count} document(s) still in progress.")
    return redirect(url_for("generation_web.package_detail", package_id=package_id))

@generation_web_bp.route("/")
@login_required
def index():
    from app.models.material_package import MaterialPackage
    from app.models.review import Notification

    Notification.query.filter_by(recipient_user_id=current_user.id, is_read=False).filter(
        Notification.link_job_id.isnot(None)
    ).update({"is_read": True})
    db.session.commit()

    syllabus_query = Syllabus.query.filter_by(organization_id=current_user.organization_id)
    if current_user.role == "user":
        syllabus_query = syllabus_query.filter_by(created_by_user_id=current_user.id)
    syllabi = syllabus_query.order_by(Syllabus.created_at.desc()).all()

    package_query = MaterialPackage.query.filter_by(organization_id=current_user.organization_id)
    if current_user.role == "user":
        package_query = package_query.filter_by(triggered_by_user_id=current_user.id)
    packages = package_query.order_by(MaterialPackage.created_at.desc()).limit(10).all()

    package_data = []
    for pkg in packages:
        syllabus = Syllabus.query.get(pkg.syllabus_id)
        review = MaterialReview.query.filter_by(package_id=pkg.id).first()
        package_data.append({"package": pkg, "title": syllabus.title if syllabus else "Unknown", "review": review})

    job_query = GenerationJob.query.filter_by(organization_id=current_user.organization_id, package_id=None)
    if current_user.role == "user":
        job_query = job_query.filter_by(triggered_by_user_id=current_user.id)
    jobs = job_query.order_by(GenerationJob.created_at.desc()).limit(20).all()

    job_syllabus_titles = {}
    job_reviews = {}
    for job in jobs:
        syllabus = Syllabus.query.get(job.syllabus_id)
        job_syllabus_titles[job.id] = syllabus.title if syllabus else "Unknown"
        job_reviews[job.id] = MaterialReview.query.filter_by(generation_job_id=job.id).first()

    return render_template(
        "generate/index.html", syllabi=syllabi, jobs=jobs,
        job_syllabus_titles=job_syllabus_titles, job_reviews=job_reviews, packages=package_data,
    )


@generation_web_bp.route("/package-job-row/<job_id>")
@login_required
def package_job_row(job_id):
    job = GenerationJob.query.filter_by(id=job_id, organization_id=current_user.organization_id).first_or_404()
    package = job.package
    review = MaterialReview.query.filter_by(package_id=package.id).first() if package else None
    can_download = not review or review.status == "approved"
    return render_template("generate/_package_job_row.html", job=job, can_download=can_download)
