"""Material generation trigger + status + download endpoints."""
from flask import Blueprint, jsonify, send_file
from flask_jwt_extended import jwt_required, get_jwt
from app.extensions import db
from app.models.syllabus import Syllabus
from app.models.generation_job import GenerationJob
from app.tasks.generation_tasks import generate_textbook_task

materials_bp = Blueprint("materials", __name__)


@materials_bp.route("/ping", methods=["GET"])
def ping():
    return jsonify({"status": "materials blueprint alive"})


@materials_bp.route("/textbook/<syllabus_id>/generate", methods=["POST"])
@jwt_required()
def trigger_textbook_generation(syllabus_id):
    """Kicks off async textbook generation. Returns immediately with a job_id to poll."""
    claims = get_jwt()
    org_id = claims.get("organization_id")

    syllabus = Syllabus.query.filter_by(id=syllabus_id, organization_id=org_id).first()
    if not syllabus:
        return jsonify({"error": "Syllabus not found"}), 404

    job = GenerationJob(organization_id=org_id, syllabus_id=syllabus_id, material_type="textbook")
    db.session.add(job)
    db.session.commit()

    generate_textbook_task.delay(job.id)

    return jsonify({"job_id": job.id, "status": job.status}), 202


@materials_bp.route("/jobs/<job_id>", methods=["GET"])
@jwt_required()
def get_job_status(job_id):
    """Poll this to check job progress: queued -> running -> done/failed."""
    claims = get_jwt()
    org_id = claims.get("organization_id")

    job = GenerationJob.query.filter_by(id=job_id, organization_id=org_id).first()
    if not job:
        return jsonify({"error": "Job not found"}), 404

    return jsonify({
        "job_id": job.id,
        "status": job.status,
        "material_type": job.material_type,
        "error_message": job.error_message,
    }), 200


@materials_bp.route("/jobs/<job_id>/download", methods=["GET"])
@jwt_required()
def download_job_result(job_id):
    claims = get_jwt()
    org_id = claims.get("organization_id")

    job = GenerationJob.query.filter_by(id=job_id, organization_id=org_id).first()
    if not job:
        return jsonify({"error": "Job not found"}), 404
    if job.status != "done":
        return jsonify({"error": f"Job is not ready yet (status: {job.status})"}), 409

    return send_file(
        job.result_file_path,
        as_attachment=True,
        download_name=f"textbook_{job.id}.docx",
        mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )