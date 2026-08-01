"""Browser-facing pages — session-based auth via Flask-Login, separate from the JWT API."""
from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from flask_login import login_user, logout_user, login_required, current_user
from app.models.user import User
from functools import wraps
from app.extensions import db
from app.models.generation_job import GenerationJob
from app.models.syllabus import Syllabus

web_bp = Blueprint("web", __name__, template_folder="../templates")


@web_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("web.dashboard"))

    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")
        user = User.query.filter_by(email=email).first()

        if user and user.check_password(password) and user.is_active:
            from flask import session
            session.permanent = True
            login_user(user)
            if user.must_change_password:
                return redirect(url_for("web.force_change_password"))
            return redirect(url_for("web.dashboard"))

        flash("Invalid email or password.")
        return redirect(url_for("web.login"))

    return render_template("login.html")


@web_bp.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("web.login"))


@web_bp.route("/")
@login_required
def dashboard():
    from app.services.storage_service import get_presigned_url
    picture_url = get_presigned_url(current_user.profile_picture_url, expires_in=300) if current_user.profile_picture_url else None

    if current_user.role == "superadmin":
        from app.models.organization import Organization
        total_orgs = Organization.query.count()
        active_orgs = Organization.query.filter_by(is_active=True).count()
        orgs = Organization.query.order_by(Organization.created_at.desc()).limit(6).all()
        return render_template("dashboard_superadmin.html", orgs=orgs, total_orgs=total_orgs, active_orgs=active_orgs, picture_url=picture_url)

    if current_user.role == "qa_reviewer":
        from app.models.review import MaterialReview
        all_reviews = MaterialReview.query.filter_by(reviewer_user_id=current_user.id).all()
        pending_count = len([r for r in all_reviews if r.status == "pending_review"])
        approved_count = len([r for r in all_reviews if r.status == "approved"])
        pending = MaterialReview.query.filter_by(reviewer_user_id=current_user.id).filter(
            MaterialReview.status != "approved"
        ).order_by(MaterialReview.created_at.desc()).limit(6).all()
        from app.models.material_package import MaterialPackage
        enriched = []
        for r in pending:
            if r.package_id:
                package = MaterialPackage.query.get(r.package_id)
                syllabus = Syllabus.query.get(package.syllabus_id) if package else None
            else:
                job = GenerationJob.query.get(r.generation_job_id)
                syllabus = Syllabus.query.get(job.syllabus_id) if job else None
            enriched.append({"review": r, "title": syllabus.title if syllabus else "Unknown"})
        return render_template("dashboard_qa.html", items=enriched, pending_count=pending_count, approved_count=approved_count, picture_url=picture_url)

    # user / org_admin
    from app.models.review import MaterialReview
    is_regular_user = current_user.role == "user"

    job_query = GenerationJob.query.filter_by(organization_id=current_user.organization_id)
    if is_regular_user:
        job_query = job_query.filter_by(triggered_by_user_id=current_user.id)
    recent_jobs = job_query.order_by(GenerationJob.created_at.desc()).limit(5).all()

    job_data = []
    for job in recent_jobs:
        syllabus = Syllabus.query.get(job.syllabus_id)
        review = MaterialReview.query.filter_by(generation_job_id=job.id).first()
        job_data.append({"job": job, "title": syllabus.title if syllabus else "Unknown", "review": review})

    syllabus_query = Syllabus.query.filter_by(organization_id=current_user.organization_id)
    if is_regular_user:
        syllabus_query = syllabus_query.filter_by(created_by_user_id=current_user.id)
    recent_syllabi = syllabus_query.order_by(Syllabus.created_at.desc()).limit(5).all()

    total_syllabi_query = Syllabus.query.filter_by(organization_id=current_user.organization_id)
    total_materials_query = GenerationJob.query.filter_by(organization_id=current_user.organization_id, status="done")
    total_approved_query = MaterialReview.query.filter_by(organization_id=current_user.organization_id, status="approved")

    if is_regular_user:
        total_syllabi_query = total_syllabi_query.filter_by(created_by_user_id=current_user.id)
        total_materials_query = total_materials_query.filter_by(triggered_by_user_id=current_user.id)
        # MaterialReview has no triggered_by field directly — scope via submitted_by_user_id instead
        total_approved_query = total_approved_query.filter_by(submitted_by_user_id=current_user.id)

    total_syllabi = total_syllabi_query.count()
    total_materials = total_materials_query.count()
    total_approved = total_approved_query.count()

    return render_template(
        "dashboard_user.html", jobs=job_data, syllabi=recent_syllabi, picture_url=picture_url,
        total_syllabi=total_syllabi, total_materials=total_materials, total_approved=total_approved,
    )

def superadmin_required(fn):
    @wraps(fn)
    @login_required
    def wrapper(*args, **kwargs):
        if current_user.role != "superadmin":
            abort(403)
        return fn(*args, **kwargs)
    return wrapper

@web_bp.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        email = request.form.get("email")
        user = User.query.filter_by(email=email).first()

        if user and user.is_active:
            from app.models.password_reset import PasswordResetRequest
            from app.models.review import Notification, prune_old_notifications

            existing = PasswordResetRequest.query.filter_by(user_id=user.id, status="pending").first()
            if not existing:
                reset_request = PasswordResetRequest(user_id=user.id)
                db.session.add(reset_request)
                db.session.flush()

                superadmins = User.query.filter_by(role="superadmin", is_active=True).all()
                for admin in superadmins:
                    db.session.add(Notification(
                        recipient_user_id=admin.id,
                        message=f"{user.email} requested a password reset.",
                    ))
                    prune_old_notifications(admin.id)
                db.session.commit()

        # Always show the same message, whether or not the email exists — avoids leaking which emails are registered
        flash("If that account exists, your administrator has been notified and will contact you with a reset code.")
        return redirect(url_for("web.login"))

    return render_template("forgot_password.html")


@web_bp.route("/reset-password", methods=["GET", "POST"])
def reset_password():
    if request.method == "POST":
        email = request.form.get("email")
        otp = request.form.get("otp")
        new_password = request.form.get("new_password")
        confirm_password = request.form.get("confirm_password")

        user = User.query.filter_by(email=email).first()
        if not user:
            flash("Invalid email or code.")
            return redirect(url_for("web.reset_password"))

        from app.models.password_reset import PasswordResetRequest
        reset_request = PasswordResetRequest.query.filter_by(
            user_id=user.id, status="approved"
        ).order_by(PasswordResetRequest.created_at.desc()).first()

        if not reset_request or not reset_request.verify_otp(otp):
            flash("Invalid or expired code.")
            return redirect(url_for("web.reset_password"))

        if not new_password or len(new_password) < 8:
            flash("Password must be at least 8 characters.")
            return redirect(url_for("web.reset_password"))
        if new_password != confirm_password:
            flash("Passwords do not match.")
            return redirect(url_for("web.reset_password"))

        user.set_password(new_password)
        reset_request.status = "used"
        db.session.commit()

        flash("Password reset successful. You can now log in.")
        return redirect(url_for("web.login"))

    return render_template("reset_password.html")

@web_bp.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    if request.method == "POST":
        current_user.first_name = request.form.get("first_name", "").strip() or None
        current_user.last_name = request.form.get("last_name", "").strip() or None

        if "profile_picture" in request.files and request.files["profile_picture"].filename:
            from app.services.storage_service import upload_file
            pic = request.files["profile_picture"]
            filename = pic.filename.lower()
            ext = filename.rsplit(".", 1)[-1] if "." in filename else "png"
            if ext in ("png", "jpg", "jpeg"):
                content_type = "image/png" if ext == "png" else "image/jpeg"
                key = f"users/{current_user.id}/profile.{ext}"
                upload_file(file_bytes=pic.read(), key=key, content_type=content_type)
                current_user.profile_picture_url = key
            else:
                flash("Profile picture must be .png, .jpg, or .jpeg")

        db.session.commit()
        flash("Profile updated.")
        return redirect(url_for("web.profile"))

    from app.services.storage_service import get_presigned_url
    picture_url = get_presigned_url(current_user.profile_picture_url, expires_in=300) if current_user.profile_picture_url else None
    return render_template("profile.html", picture_url=picture_url)


@web_bp.route("/force-change-password", methods=["GET", "POST"])
@login_required
def force_change_password():
    if not current_user.must_change_password:
        return redirect(url_for("web.dashboard"))

    if request.method == "POST":
        new_password = request.form.get("new_password")
        confirm_password = request.form.get("confirm_password")

        if not new_password or len(new_password) < 8:
            flash("Password must be at least 8 characters.")
            return redirect(url_for("web.force_change_password"))
        if new_password != confirm_password:
            flash("Passwords do not match.")
            return redirect(url_for("web.force_change_password"))

        current_user.set_password(new_password)
        current_user.must_change_password = False
        db.session.commit()
        flash("Password updated.")
        return redirect(url_for("web.dashboard"))

    return render_template("force_change_password.html")

@web_bp.route("/debug-job/<job_id>")
@login_required
def debug_job(job_id):
    from app.models.generation_job import GenerationJob
    job = GenerationJob.query.get(job_id)
    if not job:
        return {"error": "not found"}, 404
    return {
        "status": job.status,
        "error_message": job.error_message,
        "task_id": job.task_id,
        "result_file_path": job.result_file_path,
    }


@web_bp.route("/debug-latest-job")
@login_required
def debug_latest_job():
    from app.models.generation_job import GenerationJob
    job = GenerationJob.query.order_by(GenerationJob.created_at.desc()).first()
    if not job:
        return {"error": "no jobs found"}, 404
    return {
        "job_id": job.id,
        "status": job.status,
        "error_message": job.error_message,
        "task_id": job.task_id,
        "result_file_path": job.result_file_path,
        "document_subtype": job.document_subtype,
    }


@web_bp.route("/debug-latest-job/<subtype>")
@login_required
def debug_latest_job_by_type(subtype):
    if current_user.role != "superadmin":
        return {"error": "forbidden"}, 403
    from app.models.generation_job import GenerationJob
    job = GenerationJob.query.filter_by(document_subtype=subtype).order_by(GenerationJob.created_at.desc()).first()
    if not job:
        return {"error": "no jobs found for this subtype"}, 404
    return {
        "job_id": job.id,
        "status": job.status,
        "error_message": job.error_message,
        "document_subtype": job.document_subtype,
    }

