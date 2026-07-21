# Org CRUD endpoints
"""Organization (tenant) CRUD endpoints."""
from flask import Blueprint, jsonify

organizations_bp = Blueprint("organizations", __name__)


@organizations_bp.route("/ping", methods=["GET"])
def ping():
    return jsonify({"status": "organizations blueprint alive"})