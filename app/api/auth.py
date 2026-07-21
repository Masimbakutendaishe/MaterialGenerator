# Login, token refresh endpoints
"""Authentication endpoints — login, token refresh."""
from flask import Blueprint, jsonify

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/ping", methods=["GET"])
def ping():
    return jsonify({"status": "auth blueprint alive"})