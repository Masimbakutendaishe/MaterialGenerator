# Password hashing, token helpers
"""Shared security/access-control helpers used across route decorators."""
from functools import wraps
from flask import jsonify
from flask_jwt_extended import jwt_required, get_jwt, get_jwt_identity
from app.models.user import User
from app.models.organization import Organization


def active_account_required(fn):
    """Wraps @jwt_required() with checks that the user is active and, if they belong to
    an org, that the org is active and not past its trial. Use this instead of bare
    @jwt_required() on any route that generates content or accesses org data."""
    @wraps(fn)
    @jwt_required()
    def wrapper(*args, **kwargs):
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        if not user or not user.is_active:
            return jsonify({"error": "This account has been disabled"}), 403

        if user.organization_id:
            org = Organization.query.get(user.organization_id)
            if not org or not org.is_accessible():
                return jsonify({"error": "This organization's account is disabled or its trial has expired"}), 403

        return fn(*args, **kwargs)
    return wrapper


def require_role(*allowed_roles):
    """Decorator factory: restricts a route to specific roles. Use after active_account_required.
    Example: @require_role("superadmin")"""
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            claims = get_jwt()
            if claims.get("role") not in allowed_roles:
                return jsonify({"error": "You do not have permission to access this resource"}), 403
            return fn(*args, **kwargs)
        return wrapper
    return decorator