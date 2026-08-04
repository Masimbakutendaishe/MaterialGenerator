"""Syllabus web pages: list, and three intake methods (typed, upload, AI-generate)."""
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from app.extensions import db
from app.models.syllabus import Syllabus
from app.services.syllabus_service import extract_text_from_upload
from app.services.ai_service import structure_syllabus_from_text, generate_syllabus, structure_qcto_syllabus_from_text, extract_qcto_module_topics, extract_qcto_pm_details, extract_qcto_wm_details

syllabus_web_bp = Blueprint("syllabus_web", __name__, url_prefix="/syllabus")


@syllabus_web_bp.route("/")
@login_required
def list_syllabi():
    query = Syllabus.query.filter_by(organization_id=current_user.organization_id)
    if current_user.role == "user":
        query = query.filter_by(created_by_user_id=current_user.id)
    syllabi = query.order_by(Syllabus.created_at.desc()).all()
    return render_template("syllabus/list.html", syllabi=syllabi)


@syllabus_web_bp.route("/new")
@login_required
def new():
    return render_template("syllabus/new.html")


@syllabus_web_bp.route("/create-typed", methods=["POST"])
@login_required
def create_typed():
    title = request.form.get("title")
    unit_names = request.form.getlist("unit_name[]")
    unit_outcomes_raw = request.form.getlist("unit_outcomes[]")

    if not title or not unit_names:
        flash("Title and at least one unit are required.")
        return redirect(url_for("syllabus_web.new"))

    units = []
    for name, outcomes_raw in zip(unit_names, unit_outcomes_raw):
        if not name.strip():
            continue
        outcomes = [o.strip() for o in outcomes_raw.split("\n") if o.strip()]
        units.append({"name": name.strip(), "outcomes": outcomes})

    if not units:
        flash("At least one unit with a name is required.")
        return redirect(url_for("syllabus_web.new"))

    syllabus = Syllabus(
        organization_id=current_user.organization_id,
        created_by_user_id=current_user.id,
        title=title,
        source="typed",
        content={"units": units},
    )
    db.session.add(syllabus)
    db.session.commit()

    flash(f"Syllabus '{title}' created.")
    return redirect(url_for("syllabus_web.list_syllabi"))


@syllabus_web_bp.route("/create-upload", methods=["POST"])
@login_required
def create_upload():
    if "file" not in request.files or not request.files["file"].filename:
        flash("Please choose a file to upload.")
        return redirect(url_for("syllabus_web.new"))

    file_storage = request.files["file"]
    title = request.form.get("title") or file_storage.filename
    seta = request.form.get("seta")
    nqf_level = request.form.get("nqf_level")

    try:
        raw_text = extract_text_from_upload(file_storage)
    except ValueError as exc:
        flash(str(exc))
        return redirect(url_for("syllabus_web.new"))

    if not raw_text.strip():
        flash("No readable text found in the uploaded file.")
        return redirect(url_for("syllabus_web.new"))

    syllabus_type = request.form.get("syllabus_type", "standard")

    try:
        if syllabus_type == "qcto":
            content = structure_qcto_syllabus_from_text(raw_text)
            # Second pass: backfill any module whose first-pass extraction came back empty
            # (common on long documents where the first pass truncates before reaching detail)
            for module in content.get("modules", []):
                if module.get("module_type") == "KM" and not module.get("topics"):
                    module["topics"] = extract_qcto_module_topics(
                        module.get("module_code", ""), module.get("title", ""), raw_text
                    )
                elif module.get("module_type") == "PM" and not module.get("performance_assessment"):
                    pm_detail = extract_qcto_pm_details(
                        module.get("module_code", ""), module.get("title", ""), raw_text
                    )
                    module["performance_assessment"] = pm_detail.get("performance_assessment", [])
                    module["applied_knowledge"] = pm_detail.get("applied_knowledge", [])
                    module["assessment_criteria"] = pm_detail.get("assessment_criteria", [])
                elif module.get("module_type") == "WM" and not module.get("work_experience_elements"):
                    wm_detail = extract_qcto_wm_details(
                        module.get("module_code", ""), module.get("title", ""), raw_text
                    )
                    module["purpose"] = wm_detail.get("purpose") or module.get("purpose", "")
                    module["work_experience_elements"] = wm_detail.get("work_experience_elements", [])
        else:
            content = structure_syllabus_from_text(raw_text, seta=seta, nqf_level=nqf_level)
    except RuntimeError as exc:
        flash(f"AI structuring failed: {exc}")
        return redirect(url_for("syllabus_web.new"))

    syllabus = Syllabus(
        organization_id=current_user.organization_id,
        created_by_user_id=current_user.id,
        title=title,
        source="uploaded",
        content=content,
        syllabus_type=syllabus_type,
        accreditation_info={
            "seta": seta,
            "nqf_level": nqf_level,
            "qualification_code": content.get("qualification_code") if syllabus_type == "qcto" else None,
            "qualification_title": content.get("qualification_title") if syllabus_type == "qcto" else None,
        },
    )
    db.session.add(syllabus)
    db.session.commit()

    flash(f"Syllabus '{title}' created from upload.")
    return redirect(url_for("syllabus_web.list_syllabi"))


@syllabus_web_bp.route("/create-ai", methods=["POST"])
@login_required
def create_ai():
    topic = request.form.get("topic")
    seta = request.form.get("seta")
    nqf_level = request.form.get("nqf_level")

    if not topic:
        flash("Please enter a course title/topic.")
        return redirect(url_for("syllabus_web.new"))

    try:
        content = generate_syllabus(topic, seta=seta, nqf_level=nqf_level)
    except RuntimeError as exc:
        flash(f"AI generation failed: {exc}")
        return redirect(url_for("syllabus_web.new"))

    syllabus = Syllabus(
        organization_id=current_user.organization_id,
        created_by_user_id=current_user.id,
        title=topic,
        source="ai_generated",
        content=content,
        accreditation_info={"seta": seta, "nqf_level": nqf_level},
    )
    db.session.add(syllabus)
    db.session.commit()

    flash(f"Syllabus '{topic}' generated.")
    return redirect(url_for("syllabus_web.list_syllabi"))



@syllabus_web_bp.route("/<syllabus_id>")
@login_required
def detail(syllabus_id):
    syllabus = Syllabus.query.filter_by(id=syllabus_id, organization_id=current_user.organization_id).first_or_404()
    if current_user.role == "user" and syllabus.created_by_user_id != current_user.id:
        flash("You do not have access to that syllabus.")
        return redirect(url_for("syllabus_web.list_syllabi"))
    return render_template("syllabus/detail.html", syllabus=syllabus)