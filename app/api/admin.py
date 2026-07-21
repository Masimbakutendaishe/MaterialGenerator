# Superadmin: org provisioning
"""Platform-admin endpoints — superadmin only. Creates and manages organizations and their users."""
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify
from app.extensions import db
from app.models.organization import Organization
from app.models.user import User, VALID_ROLES
from app.utils.security import active_account_required, require_role

admin_bp = Blueprint("admin", __name__)


@admin_bp.route("/organizations", methods=["POST"])
@active_account_required
@require_role("superadmin")
def create_organization():
    """Creates an organization, optionally with a trial period (trial_days)."""
    data = request.get_json() or {}
    name = data.get("name")
    if not name:
        return jsonify({"error": "name is required"}), 400

    trial_days = data.get("trial_days")
    trial_ends_at = None
    if trial_days:
        trial_ends_at = datetime.utcnow() + timedelta(days=int(trial_days))

    org = Organization(name=name, plan=data.get("plan", "trial"), trial_ends_at=trial_ends_at)
    db.session.add(org)
    db.session.commit()

    return jsonify({
        "id": org.id, "name": org.name, "plan": org.plan,
        "trial_ends_at": org.trial_ends_at.isoformat() if org.trial_ends_at else None,
        "is_active": org.is_active,
    }), 201


@admin_bp.route("/organizations/<org_id>", methods=["PATCH"])
@active_account_required
@require_role("superadmin")
def update_organization(org_id):
    """Enable/disable an org, or change its trial expiry / plan."""
    org = Organization.query.get(org_id)
    if not org:
        return jsonify({"error": "Organization not found"}), 404

    data = request.get_json() or {}
    if "is_active" in data:
        org.is_active = bool(data["is_active"])
    if "plan" in data:
        org.plan = data["plan"]
    if "trial_days" in data:
        org.trial_ends_at = datetime.utcnow() + timedelta(days=int(data["trial_days"])) if data["trial_days"] else None

    db.session.commit()
    return jsonify({
        "id": org.id, "name": org.name, "plan": org.plan,
        "trial_ends_at": org.trial_ends_at.isoformat() if org.trial_ends_at else None,
        "is_active": org.is_active,
    }), 200


@admin_bp.route("/organizations/<org_id>/users", methods=["POST"])
@active_account_required
@require_role("superadmin")
def create_user_in_organization(org_id):
    """Creates a user inside a specific organization, with a role and optional QA assignment."""
    org = Organization.query.get(org_id)
    if not org:
        return jsonify({"error": "Organization not found"}), 404

    data = request.get_json() or {}
    email = data.get("email")
    password = data.get("password")
    role = data.get("role", "user")
    reports_to_user_id = data.get("reports_to_user_id")

    if not email or not password:
        return jsonify({"error": "email and password are required"}), 400
    if role not in VALID_ROLES:
        return jsonify({"error": f"role must be one of {VALID_ROLES}"}), 400
    if User.query.filter_by(email=email).first():
        return jsonify({"error": "A user with that email already exists"}), 409

    if reports_to_user_id:
        supervisor = User.query.filter_by(id=reports_to_user_id, organization_id=org_id).first()
        if not supervisor:
            return jsonify({"error": "reports_to_user_id must be a user in the same organization"}), 400

    user = User(organization_id=org_id, email=email, role=role, reports_to_user_id=reports_to_user_id)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()

    return jsonify({"id": user.id, "email": user.email, "role": user.role, "reports_to_user_id": user.reports_to_user_id}), 201


@admin_bp.route("/users/<user_id>", methods=["PATCH"])
@active_account_required
@require_role("superadmin")
def update_user(user_id):
    """Enable/disable a user, or reassign their role or QA reviewer."""
    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404

    data = request.get_json() or {}
    if "is_active" in data:
        user.is_active = bool(data["is_active"])
    if "role" in data:
        if data["role"] not in VALID_ROLES:
            return jsonify({"error": f"role must be one of {VALID_ROLES}"}), 400
        user.role = data["role"]
    if "reports_to_user_id" in data:
        user.reports_to_user_id = data["reports_to_user_id"]

    db.session.commit()
    return jsonify({"id": user.id, "email": user.email, "role": user.role, "is_active": user.is_active}), 200