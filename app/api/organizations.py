"""Organization (tenant) endpoints."""
from flask import Blueprint, jsonify
from flask_jwt_extended import jwt_required, get_jwt, get_jwt_identity
from app.models.organization import Organization
from app.models.user import User

organizations_bp = Blueprint("organizations", __name__)


@organizations_bp.route("/ping", methods=["GET"])
def ping():
    return jsonify({"status": "organizations blueprint alive"})


@organizations_bp.route("/me", methods=["GET"])
@jwt_required()
def get_my_organization():
    """Returns the organization of whoever's JWT is presented — never any other org's data."""
    claims = get_jwt()
    org_id = claims.get("organization_id")

    if not org_id:
        return jsonify({"error": "This account is not attached to an organization"}), 403

    org = Organization.query.get(org_id)
    if not org:
        return jsonify({"error": "Organization not found"}), 404

    return jsonify({
        "id": org.id,
        "name": org.name,
        "plan": org.plan,
        "logo_url": org.logo_url,
        "brand_colors": org.brand_colors,
    }), 200


@organizations_bp.route("/me/users", methods=["GET"])
@jwt_required()
def list_my_organization_users():
    """Lists users belonging to the caller's organization only — the core of tenant isolation."""
    claims = get_jwt()
    org_id = claims.get("organization_id")

    if not org_id:
        return jsonify({"error": "This account is not attached to an organization"}), 403

    users = User.query.filter_by(organization_id=org_id).all()
    return jsonify([{"id": u.id, "email": u.email, "role": u.role} for u in users]), 200