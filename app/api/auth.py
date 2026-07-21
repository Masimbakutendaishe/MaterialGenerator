"""Authentication endpoints — register, login, token refresh."""
from flask import Blueprint, request, jsonify
from flask_jwt_extended import create_access_token
from app.extensions import db
from app.models.organization import Organization
from app.models.user import User

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/ping", methods=["GET"])
def ping():
    return jsonify({"status": "auth blueprint alive"})


@auth_bp.route("/register-organization", methods=["POST"])
def register_organization():
    """Creates a new Organization plus its first org_admin user. Used when you (the platform admin) onboard a new client."""
    data = request.get_json() or {}
    org_name = data.get("organization_name")
    email = data.get("email")
    password = data.get("password")

    if not org_name or not email or not password:
        return jsonify({"error": "organization_name, email, and password are required"}), 400

    if User.query.filter_by(email=email).first():
        return jsonify({"error": "A user with that email already exists"}), 409

    org = Organization(name=org_name)
    db.session.add(org)
    db.session.flush()  # so org.id is available before creating the user

    user = User(organization_id=org.id, email=email, role="org_admin")
    user.set_password(password)
    db.session.add(user)
    db.session.commit()

    return jsonify({"organization_id": org.id, "user_id": user.id, "email": user.email}), 201


@auth_bp.route("/login", methods=["POST"])
def login():
    data = request.get_json() or {}
    email = data.get("email")
    password = data.get("password")

    user = User.query.filter_by(email=email).first()
    if not user or not user.check_password(password) or not user.is_active:
        return jsonify({"error": "Invalid credentials"}), 401

    token = create_access_token(
        identity=user.id,
        additional_claims={"organization_id": user.organization_id, "role": user.role},
    )
    return jsonify({"access_token": token}), 200