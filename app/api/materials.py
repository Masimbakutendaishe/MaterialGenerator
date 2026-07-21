# Material generation trigger + status + download endpoints
"""Material generation trigger / status / download endpoints."""
from flask import Blueprint, jsonify

materials_bp = Blueprint("materials", __name__)


@materials_bp.route("/ping", methods=["GET"])
def ping():
    return jsonify({"status": "materials blueprint alive"})