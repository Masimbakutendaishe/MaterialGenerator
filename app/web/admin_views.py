"""Superadmin web console — create/manage organizations and their users."""
from datetime import datetime, timedelta
from flask import Blueprint, render_template, request, redirect, url_for, flash
from app.web.views import superadmin_required
from app.extensions import db
from app.models.organization import Organization
from app.models.user import User, VALID_ROLES
from flask_login import current_user

web_admin_bp = Blueprint("web_admin", __name__, url_prefix="/admin")


@web_admin_bp.route("/")
@superadmin_required
def organizations():
    from datetime import datetime, timezone
    from app.models.generation_job import GenerationJob
    from app.models.material_package import MaterialPackage
    from sqlalchemy import func

    orgs = Organization.query.order_by(Organization.created_at.desc()).all()

    month_start = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    usage = {}
    for org in orgs:
        # Standalone singular documents ONLY — explicitly excludes anything generated as
        # part of a package, since those are counted separately below.
        singles_total = GenerationJob.query.filter_by(organization_id=org.id, status="done", package_id=None).count()
        singles_month = GenerationJob.query.filter(
            GenerationJob.organization_id == org.id,
            GenerationJob.status == "done",
            GenerationJob.package_id.is_(None),
            GenerationJob.created_at >= month_start,
        ).count()
        packages_total = MaterialPackage.query.filter_by(organization_id=org.id).count()
        packages_month = MaterialPackage.query.filter(
            MaterialPackage.organization_id == org.id,
            MaterialPackage.created_at >= month_start,
        ).count()
        usage[org.id] = {
            "singles_total": singles_total,
            "singles_month": singles_month,
            "packages_total": packages_total,
            "packages_month": packages_month,
        }

    return render_template("admin/organizations.html", orgs=orgs, usage=usage)


@web_admin_bp.route("/organizations", methods=["POST"])
@superadmin_required
def create_organization():
    name = request.form.get("name")
    trial_days = request.form.get("trial_days")

    if not name:
        flash("Organization name is required.")
        return redirect(url_for("web_admin.organizations"))

    trial_ends_at = datetime.utcnow() + timedelta(days=int(trial_days)) if trial_days else None
    org = Organization(name=name, plan="trial", trial_ends_at=trial_ends_at)
    db.session.add(org)
    db.session.commit()

    flash(f"Organization '{name}' created.")
    return redirect(url_for("web_admin.organizations"))


@web_admin_bp.route("/organizations/<org_id>")
@superadmin_required
def organization_detail(org_id):
    from app.models.plan import Plan
    org = Organization.query.get_or_404(org_id)
    users = User.query.filter_by(organization_id=org_id).order_by(User.created_at.desc()).all()
    qa_reviewers = User.query.filter_by(organization_id=org_id, role="qa_reviewer").all()
    plans = Plan.query.filter_by(is_active=True).order_by(Plan.price_zar.asc()).all()
    return render_template("admin/organization_detail.html", org=org, users=users, valid_roles=VALID_ROLES, qa_reviewers=qa_reviewers, plans=plans)


@web_admin_bp.route("/organizations/<org_id>/toggle", methods=["POST"])
@superadmin_required
def toggle_organization(org_id):
    org = Organization.query.get_or_404(org_id)
    org.is_active = not org.is_active
    db.session.commit()
    flash(f"Organization '{org.name}' {'enabled' if org.is_active else 'disabled'}.")
    return redirect(url_for("web_admin.organization_detail", org_id=org_id))

@web_admin_bp.route("/organizations/<org_id>/plan", methods=["POST"])
@superadmin_required
def set_organization_plan(org_id):
    org = Organization.query.get_or_404(org_id)
    plan_id = request.form.get("plan_id") or None
    org.plan_id = plan_id
    db.session.commit()
    flash(f"Plan updated for '{org.name}'.")
    return redirect(url_for("web_admin.organization_detail", org_id=org_id))


@web_admin_bp.route("/organizations/<org_id>/extend-trial", methods=["POST"])
@superadmin_required
def extend_trial(org_id):
    org = Organization.query.get_or_404(org_id)
    trial_ends_at = request.form.get("trial_ends_at")
    if trial_ends_at:
        from datetime import datetime
        org.trial_ends_at = datetime.strptime(trial_ends_at, "%Y-%m-%d")
        db.session.commit()
        flash(f"Trial date updated for '{org.name}'.")
    else:
        flash("Please select a date.")
    return redirect(url_for("web_admin.organization_detail", org_id=org_id))


@web_admin_bp.route("/organizations/<org_id>/override", methods=["POST"])
@superadmin_required
def toggle_override(org_id):
    org = Organization.query.get_or_404(org_id)
    org.force_active_override = not org.force_active_override
    db.session.commit()
    flash(f"Manual override {'activated' if org.force_active_override else 'removed'} for '{org.name}'.")
    return redirect(url_for("web_admin.organization_detail", org_id=org_id))


@web_admin_bp.route("/organizations/<org_id>/users", methods=["POST"])
@superadmin_required
def create_user(org_id):
    org = Organization.query.get_or_404(org_id)
    email = request.form.get("email")
    password = request.form.get("password")
    role = request.form.get("role", "user")

    if not email or not password:
        flash("Email and password are required.")
        return redirect(url_for("web_admin.organization_detail", org_id=org_id))

    if role not in VALID_ROLES:
        flash("Invalid role.")
        return redirect(url_for("web_admin.organization_detail", org_id=org_id))

    if User.query.filter_by(email=email).first():
        flash(f"A user with email '{email}' already exists.")
        return redirect(url_for("web_admin.organization_detail", org_id=org_id))

    user = User(organization_id=org_id, email=email, role=role, must_change_password=True)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()

    flash(f"User '{email}' created.")
    return redirect(url_for("web_admin.organization_detail", org_id=org_id))


@web_admin_bp.route("/users/<user_id>/toggle", methods=["POST"])
@superadmin_required
def toggle_user(user_id):
    user = User.query.get_or_404(user_id)
    user.is_active = not user.is_active
    db.session.commit()
    flash(f"User '{user.email}' {'enabled' if user.is_active else 'disabled'}.")
    return redirect(url_for("web_admin.organization_detail", org_id=user.organization_id))

@web_admin_bp.route("/password-resets")
@superadmin_required
def password_resets():
    from app.models.password_reset import PasswordResetRequest
    pending = PasswordResetRequest.query.filter_by(status="pending").order_by(PasswordResetRequest.created_at.desc()).all()
    approved = PasswordResetRequest.query.filter_by(status="approved").order_by(PasswordResetRequest.created_at.desc()).all()
    return render_template("admin/password_resets.html", pending=pending, approved=approved)

@web_admin_bp.route("/password-resets/<request_id>/approve", methods=["POST"])
@superadmin_required
def approve_password_reset(request_id):
    from app.models.password_reset import PasswordResetRequest
    reset_request = PasswordResetRequest.query.get_or_404(request_id)
    reset_request.status = "approved"
    reset_request.approved_by_user_id = current_user.id
    otp_code = reset_request.generate_otp()
    db.session.commit()

    return render_template("admin/otp_display.html", user_email=reset_request.user.email, otp_code=otp_code)


@web_admin_bp.route("/password-resets/<request_id>/deny", methods=["POST"])
@superadmin_required
def deny_password_reset(request_id):
    from app.models.password_reset import PasswordResetRequest
    reset_request = PasswordResetRequest.query.get_or_404(request_id)
    reset_request.status = "denied"
    db.session.commit()
    flash("Reset request denied.")
    return redirect(url_for("web_admin.password_resets"))

@web_admin_bp.route("/users/<user_id>/set-reports-to", methods=["POST"])
@superadmin_required
def set_reports_to(user_id):
    user = User.query.get_or_404(user_id)
    reports_to_user_id = request.form.get("reports_to_user_id") or None

    if reports_to_user_id:
        supervisor = User.query.filter_by(id=reports_to_user_id, organization_id=user.organization_id, role="qa_reviewer").first()
        if not supervisor:
            flash("Invalid QA reviewer selection.")
            return redirect(url_for("web_admin.organization_detail", org_id=user.organization_id))

    user.reports_to_user_id = reports_to_user_id
    db.session.commit()
    flash(f"Updated who {user.email} reports to.")
    return redirect(url_for("web_admin.organization_detail", org_id=user.organization_id))