"""Branding page: upload logo and set brand colors for the current user's organization."""
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from app.extensions import db
from app.models.organization import Organization
from app.services.storage_service import upload_file, get_presigned_url

branding_web_bp = Blueprint("branding_web", __name__, url_prefix="/branding")


@branding_web_bp.route("/")
@login_required
def branding():
    org = Organization.query.get(current_user.organization_id)
    logo_url = None
    if org and org.logo_url:
        logo_url = get_presigned_url(org.logo_url, expires_in=300)
    return render_template("branding/index.html", org=org, logo_url=logo_url)


@branding_web_bp.route("/update", methods=["POST"])
@login_required
def update():
    org = Organization.query.get(current_user.organization_id)
    if not org:
        flash("No organization found for your account.")
        return redirect(url_for("branding_web.branding"))

    if "logo" in request.files and request.files["logo"].filename:
        logo_file = request.files["logo"]
        filename = logo_file.filename.lower()
        ext = filename.rsplit(".", 1)[-1] if "." in filename else "png"
        if ext not in ("png", "jpg", "jpeg"):
            flash("Logo must be .png, .jpg, or .jpeg")
            return redirect(url_for("branding_web.branding"))

        content_type = "image/png" if ext == "png" else "image/jpeg"
        logo_key = f"{org.id}/branding/logo.{ext}"
        upload_file(file_bytes=logo_file.read(), key=logo_key, content_type=content_type)
        org.logo_url = logo_key

    primary = request.form.get("primary")
    secondary = request.form.get("secondary")
    accent = request.form.get("accent")
    if primary or secondary or accent:
        org.brand_colors = {
            "primary": primary or (org.brand_colors or {}).get("primary"),
            "secondary": secondary or (org.brand_colors or {}).get("secondary"),
            "accent": accent or (org.brand_colors or {}).get("accent"),
        }

    db.session.commit()
    flash("Branding updated.")
    return redirect(url_for("branding_web.branding"))