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

from flask import request
import json as json_lib
from app.extensions import db
from app.services.storage_service import upload_file


@organizations_bp.route("/me/branding", methods=["POST"])
@jwt_required()
def update_branding():
    """Upload a logo and/or set brand colors for the caller's organization.
    Send as multipart/form-data: 'logo' (file, optional), 'colors' (JSON string, optional)."""
    claims = get_jwt()
    org_id = claims.get("organization_id")

    org = Organization.query.get(org_id)
    if not org:
        return jsonify({"error": "Organization not found"}), 404

    if "logo" in request.files and request.files["logo"].filename:
        logo_file = request.files["logo"]
        filename = logo_file.filename.lower()
        ext = filename.rsplit(".", 1)[-1] if "." in filename else "png"
        if ext not in ("png", "jpg", "jpeg"):
            return jsonify({"error": "Logo must be .png, .jpg, or .jpeg"}), 400

        content_type = "image/png" if ext == "png" else "image/jpeg"
        logo_key = f"{org_id}/branding/logo.{ext}"
        upload_file(file_bytes=logo_file.read(), key=logo_key, content_type=content_type)
        org.logo_url = logo_key  # stores the storage KEY, not a public URL — fetched via storage_service when needed

    colors_raw = request.form.get("colors")
    if colors_raw:
        try:
            org.brand_colors = json_lib.loads(colors_raw)
        except json_lib.JSONDecodeError:
            return jsonify({"error": "colors must be valid JSON, e.g. {\"primary\": \"#1a5276\"}"}), 400

    db.session.commit()

    return jsonify({
        "id": org.id,
        "name": org.name,
        "logo_url": org.logo_url,
        "brand_colors": org.brand_colors,
    }), 200