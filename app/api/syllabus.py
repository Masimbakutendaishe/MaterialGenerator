# Syllabus upload/type-in/AI-generate endpoints
"""Syllabus upload / type-in / AI-generate endpoints."""
from flask import Blueprint, jsonify

syllabus_bp = Blueprint("syllabus", __name__)


@syllabus_bp.route("/ping", methods=["GET"])
def ping():
    return jsonify({"status": "syllabus blueprint alive"})