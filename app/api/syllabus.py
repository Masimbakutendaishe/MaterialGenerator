"""Syllabus upload / type-in / AI-generate endpoints."""
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt, get_jwt_identity
from app.extensions import db
from app.models.syllabus import Syllabus
from app.services.ai_service import generate_syllabus
syllabus_bp = Blueprint("syllabus", __name__)


@syllabus_bp.route("/ping", methods=["GET"])
def ping():
    return jsonify({"status": "syllabus blueprint alive"})


@syllabus_bp.route("", methods=["POST"])
@jwt_required()
def create_syllabus_typed():
    """Type-in path: the org submits structured syllabus content directly."""
    claims = get_jwt()
    org_id = claims.get("organization_id")
    user_id = get_jwt_identity()

    if not org_id:
        return jsonify({"error": "This account is not attached to an organization"}), 403

    data = request.get_json() or {}
    title = data.get("title")
    content = data.get("content")

    if not title or not content:
        return jsonify({"error": "title and content are required"}), 400

    syllabus = Syllabus(
        organization_id=org_id,
        created_by_user_id=user_id,
        title=title,
        source="typed",
        content=content,
        accreditation_info=data.get("accreditation_info"),
    )
    db.session.add(syllabus)
    db.session.commit()

    return jsonify({"id": syllabus.id, "title": syllabus.title, "status": syllabus.status}), 201


@syllabus_bp.route("", methods=["GET"])
@jwt_required()
def list_syllabi():
    """Lists syllabi belonging to the caller's organization only."""
    claims = get_jwt()
    org_id = claims.get("organization_id")

    syllabi = Syllabus.query.filter_by(organization_id=org_id).order_by(Syllabus.created_at.desc()).all()
    return jsonify([
        {"id": s.id, "title": s.title, "source": s.source, "status": s.status, "created_at": s.created_at.isoformat()}
        for s in syllabi
    ]), 200


@syllabus_bp.route("/<syllabus_id>", methods=["GET"])
@jwt_required()
def get_syllabus(syllabus_id):
    """Fetches one syllabus — scoped so orgs can never read each other's syllabi."""
    claims = get_jwt()
    org_id = claims.get("organization_id")

    syllabus = Syllabus.query.filter_by(id=syllabus_id, organization_id=org_id).first()
    if not syllabus:
        return jsonify({"error": "Syllabus not found"}), 404

    return jsonify({
        "id": syllabus.id,
        "title": syllabus.title,
        "source": syllabus.source,
        "content": syllabus.content,
        "accreditation_info": syllabus.accreditation_info,
        "status": syllabus.status,
    }), 200


@syllabus_bp.route("/generate", methods=["POST"])
@jwt_required()
def create_syllabus_ai_generated():
    """AI-generate path: given just a topic (and optional SETA/NQF context), produces a draft syllabus."""
    claims = get_jwt()
    org_id = claims.get("organization_id")
    user_id = get_jwt_identity()

    if not org_id:
        return jsonify({"error": "This account is not attached to an organization"}), 403

    data = request.get_json() or {}
    topic = data.get("topic")
    if not topic:
        return jsonify({"error": "topic is required"}), 400

    try:
        content = generate_syllabus(
            topic=topic,
            seta=data.get("seta"),
            nqf_level=data.get("nqf_level"),
        )
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 502

    syllabus = Syllabus(
        organization_id=org_id,
        created_by_user_id=user_id,
        title=data.get("title", topic),
        source="ai_generated",
        content=content,
        accreditation_info={"seta": data.get("seta"), "nqf_level": data.get("nqf_level")},
    )
    db.session.add(syllabus)
    db.session.commit()

    return jsonify({"id": syllabus.id, "title": syllabus.title, "status": syllabus.status, "content": content}), 201