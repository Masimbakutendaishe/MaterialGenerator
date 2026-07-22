"""Superadmin web console — create/manage organizations and their users."""
from datetime import datetime, timedelta
from flask import Blueprint, render_template, request, redirect, url_for, flash
from app.web.views import superadmin_required
from app.extensions import db
from app.models.organization import Organization
from app.models.user import User, VALID_ROLES

web_admin_bp = Blueprint("web_admin", __name__, url_prefix="/admin")


@web_admin_bp.route("/")
@superadmin_required
def organizations():
    orgs = Organization.query.order_by(Organization.created_at.desc()).all()
    return render_template("admin/organizations.html", orgs=orgs)


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
    org = Organization.query.get_or_404(org_id)
    users = User.query.filter_by(organization_id=org_id).order_by(User.created_at.desc()).all()
    return render_template("admin/organization_detail.html", org=org, users=users, valid_roles=VALID_ROLES)


@web_admin_bp.route("/organizations/<org_id>/toggle", methods=["POST"])
@superadmin_required
def toggle_organization(org_id):
    org = Organization.query.get_or_404(org_id)
    org.is_active = not org.is_active
    db.session.commit()
    flash(f"Organization '{org.name}' {'enabled' if org.is_active else 'disabled'}.")
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

    user = User(organization_id=org_id, email=email, role=role)
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