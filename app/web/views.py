"""Browser-facing pages — session-based auth via Flask-Login, separate from the JWT API."""
from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from flask_login import login_user, logout_user, login_required, current_user
from app.models.user import User
from functools import wraps


web_bp = Blueprint("web", __name__, template_folder="../templates")


@web_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("web.dashboard"))

    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")
        user = User.query.filter_by(email=email).first()

        if user and user.check_password(password) and user.is_active:
            login_user(user)
            return redirect(url_for("web.dashboard"))

        flash("Invalid email or password.")
        return redirect(url_for("web.login"))

    return render_template("login.html")


@web_bp.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("web.login"))


@web_bp.route("/")
@login_required
def dashboard():
    return render_template("dashboard.html", user=current_user)

def superadmin_required(fn):
    @wraps(fn)
    @login_required
    def wrapper(*args, **kwargs):
        if current_user.role != "superadmin":
            abort(403)
        return fn(*args, **kwargs)
    return wrapper