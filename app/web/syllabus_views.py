"""Syllabus web pages: list, and three intake methods (typed, upload, AI-generate)."""
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from app.extensions import db
from app.models.syllabus import Syllabus
from app.services.syllabus_service import extract_text_from_upload
from app.services.ai_service import structure_syllabus_from_text, generate_syllabus

syllabus_web_bp = Blueprint("syllabus_web", __name__, url_prefix="/syllabus")


@syllabus_web_bp.route("/")
@login_required
def list_syllabi():
    query = Syllabus.query.filter_by(organization_id=current_user.organization_id)
    if current_user.role == "user":
        query = query.filter_by(created_by_user_id=current_user.id)
    syllabi = query.order_by(Syllabus.created_at.desc()).all()
    return render_template("syllabus/list.html", syllabi=syllabi)
@syllabus_web_bp.route("/create-typed-qcto", methods=["POST"])
@login_required
def create_typed_qcto():
    title = request.form.get("title")
    seta = request.form.get("seta")
    nqf_level = request.form.get("nqf_level")
    saqa_id = request.form.get("saqa_id")

    if not title:
        flash("Please enter a qualification title.")
        return redirect(url_for("syllabus_web.new"))

    modules = []
    m = 0
    while request.form.get(f"module-{m}-type") is not None:
        module_type = request.form.get(f"module-{m}-type", "").strip()
        module = {
            "module_type": module_type,
            "module_code": request.form.get(f"module-{m}-code", "").strip(),
            "title": request.form.get(f"module-{m}-title", "").strip(),
            "nqf_level": request.form.get(f"module-{m}-nqf", "").strip(),
            "credits": request.form.get(f"module-{m}-credits", "").strip(),
        }

        if module_type == "KM":
            topics = []
            t = 0
            while request.form.get(f"module-{m}-topic-{t}-title") is not None:
                topic_title = request.form.get(f"module-{m}-topic-{t}-title", "").strip()
                if topic_title:
                    elements = []
                    e = 0
                    while request.form.get(f"module-{m}-topic-{t}-element-{e}-text") is not None:
                        el_text = request.form.get(f"module-{m}-topic-{t}-element-{e}-text", "").strip()
                        if el_text:
                            elements.append({
                                "code": request.form.get(f"module-{m}-topic-{t}-element-{e}-code", "").strip(),
                                "text": el_text,
                            })
                        e += 1
                    topics.append({
                        "topic_code": request.form.get(f"module-{m}-topic-{t}-code", "").strip(),
                        "title": topic_title,
                        "elements": elements,
                    })
                t += 1
            module["topics"] = topics

        elif module_type == "PM":
            pa_items = []
            p = 0
            while request.form.get(f"module-{m}-pa-{p}-text") is not None:
                pa_text = request.form.get(f"module-{m}-pa-{p}-text", "").strip()
                if pa_text:
                    pa_items.append({
                        "code": request.form.get(f"module-{m}-pa-{p}-code", "").strip(),
                        "text": pa_text,
                    })
                p += 1
            module["performance_assessment"] = pa_items

        elif module_type == "WM":
            we_items = []
            w = 0
            while request.form.get(f"module-{m}-we-{w}-text") is not None:
                we_text = request.form.get(f"module-{m}-we-{w}-text", "").strip()
                if we_text:
                    we_items.append(we_text)
                w += 1
            module["work_experience_elements"] = we_items

        if module["title"]:
            modules.append(module)
        m += 1

    if not modules:
        flash("Please add at least one module with a title.")
        return redirect(url_for("syllabus_web.new"))

    syllabus = Syllabus(
        organization_id=current_user.organization_id,
        created_by_user_id=current_user.id,
        title=title,
        source="typed",
        syllabus_type="qcto",
        content={"qualification_title": title, "modules": modules},
        accreditation_info={"seta": seta, "nqf_level": nqf_level, "saqa_id": saqa_id},
        status="draft",
    )
    db.session.add(syllabus)
    db.session.commit()
    flash(f"'{title}' created successfully.")
    return redirect(url_for("syllabus_web.detail", syllabus_id=syllabus.id))



@syllabus_web_bp.route("/new")
@login_required
def new():
    from app.services.seta_constants import SETA_CHOICES
    return render_template("syllabus/new.html", seta_choices=SETA_CHOICES)


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
    title = request.form.get("title")
    seta = request.form.get("seta")
    nqf_level = request.form.get("nqf_level")
    saqa_id = request.form.get("saqa_id")
    syllabus_type = request.form.get("syllabus_type", "standard")

    # Store the original uploaded file so it can be viewed later for comparison against generated output
    file_storage.stream.seek(0)
    original_bytes = file_storage.stream.read()
    file_storage.stream.seek(0)

    try:
        raw_text = extract_text_from_upload(file_storage)
    except ValueError as exc:
        flash(str(exc))
        return redirect(url_for("syllabus_web.new"))

    if not raw_text.strip():
        flash("No readable text found in the uploaded file.")
        return redirect(url_for("syllabus_web.new"))

    if not title:
        from app.services.ai_service import derive_title_from_text
        title = derive_title_from_text(raw_text)

    if syllabus_type == "qcto":
        # QCTO extraction can take a while (many sequential AI calls) - create the
        # syllabus immediately as "processing" and hand off to the background worker.
        from app.tasks.syllabus_tasks import process_qcto_syllabus_task

        syllabus = Syllabus(
            organization_id=current_user.organization_id,
            created_by_user_id=current_user.id,
            title=title,
            source="uploaded",
            content={},
            syllabus_type="qcto",
            status="processing",
            accreditation_info={"seta": seta, "nqf_level": nqf_level, "saqa_id": saqa_id},
        )
        db.session.add(syllabus)
        db.session.flush()

        from app.services.storage_service import upload_file
        file_key = f"{current_user.organization_id}/syllabi/{syllabus.id}_{file_storage.filename}"
        upload_file(original_bytes, file_key, file_storage.mimetype or "application/pdf")
        syllabus.original_file_key = file_key
        db.session.commit()

        process_qcto_syllabus_task.delay(syllabus.id, raw_text)

        flash("Your curriculum is being processed in the background - you'll be notified once it's ready.")
        return redirect(url_for("syllabus_web.list_syllabi"))

    # Standard uploads were previously kept synchronous, but a long or multi-chunk
    # document being extracted via AI could still exceed the platform's gateway
    # timeout, causing a 502 while leaving the browser's modal stuck saying
    # "Generating" indefinitely. Moved to background processing, matching the QCTO
    # upload path, so the request returns immediately and the row-level spinner
    # reflects real progress instead.
    from app.tasks.syllabus_tasks import process_standard_syllabus_task

    syllabus = Syllabus(
        organization_id=current_user.organization_id,
        created_by_user_id=current_user.id,
        title=title,
        source="uploaded",
        content={},
        syllabus_type="standard",
        status="processing",
        accreditation_info={"seta": seta, "nqf_level": nqf_level, "saqa_id": saqa_id},
    )
    db.session.add(syllabus)
    db.session.flush()

    from app.services.storage_service import upload_file
    file_key = f"{current_user.organization_id}/syllabi/{syllabus.id}_{file_storage.filename}"
    upload_file(original_bytes, file_key, file_storage.mimetype or "application/pdf")
    syllabus.original_file_key = file_key
    db.session.commit()

    process_standard_syllabus_task.delay(syllabus.id, raw_text, seta, nqf_level)

    flash("Your syllabus is being processed in the background — you'll be notified once it's ready.")
    return redirect(url_for("syllabus_web.list_syllabi"))


@syllabus_web_bp.route("/create-ai", methods=["POST"])
@login_required
def create_ai():
    topic = request.form.get("topic")
    seta = request.form.get("seta")
    nqf_level = request.form.get("nqf_level")
    saqa_id = request.form.get("saqa_id")

    if not topic:
        flash("Please enter a course title/topic.")
        return redirect(url_for("syllabus_web.new"))

    from app.tasks.syllabus_tasks import process_ai_generate_syllabus_task

    syllabus = Syllabus(
        organization_id=current_user.organization_id,
        created_by_user_id=current_user.id,
        title=topic,
        source="ai_generated",
        content={},
        status="processing",
        accreditation_info={"seta": seta, "nqf_level": nqf_level, "saqa_id": saqa_id},
    )
    db.session.add(syllabus)
    db.session.commit()

    process_ai_generate_syllabus_task.delay(syllabus.id, topic, seta, nqf_level)
    flash(f"'{topic}' is being generated in the background, you'll be notified once it's ready.")
    return redirect(url_for("syllabus_web.list_syllabi"))



@syllabus_web_bp.route("/<syllabus_id>/cancel", methods=["POST"])
@login_required
def cancel_processing(syllabus_id):
    syllabus = Syllabus.query.filter_by(id=syllabus_id, organization_id=current_user.organization_id).first_or_404()
    if syllabus.status != "processing":
        flash("This curriculum is not currently processing.")
        return redirect(url_for("syllabus_web.detail", syllabus_id=syllabus_id))

    syllabus.status = "cancelled"
    db.session.commit()
    flash("Cancellation requested, processing will stop after the current step finishes.")
    return redirect(url_for("syllabus_web.list_syllabi"))


@syllabus_web_bp.route("/<syllabus_id>")
@login_required
def detail(syllabus_id):
    syllabus = Syllabus.query.filter_by(id=syllabus_id, organization_id=current_user.organization_id).first_or_404()
    if current_user.role == "user" and syllabus.created_by_user_id != current_user.id:
        flash("You do not have access to that syllabus.")
        return redirect(url_for("syllabus_web.list_syllabi"))
    return render_template("syllabus/detail.html", syllabus=syllabus)

@syllabus_web_bp.route("/<syllabus_id>/delete", methods=["POST"])
@login_required
def delete_syllabus(syllabus_id):
    from app.models.generation_job import GenerationJob
    from app.models.material_package import MaterialPackage
    from app.models.review import MaterialReview

    syllabus = Syllabus.query.filter_by(id=syllabus_id, organization_id=current_user.organization_id).first()
    if not syllabus:
        flash("Syllabus not found.")
        return redirect(url_for("syllabus_web.list_syllabi"))
    if current_user.role == "user" and syllabus.created_by_user_id != current_user.id:
        flash("You do not have access to that syllabus.")
        return redirect(url_for("syllabus_web.list_syllabi"))

    # Foreign keys on GenerationJob/MaterialPackage are NOT NULL with no database-level
    # cascade configured, so dependent records must be removed in the right order before
    # the syllabus itself can be deleted: reviews first (using proper ORM deletion, not a
    # bulk query, so MaterialReview's own cascade to its comments actually fires), then
    # the jobs/packages that generated them, then finally the syllabus.
    jobs = GenerationJob.query.filter_by(syllabus_id=syllabus_id).all()
    packages = MaterialPackage.query.filter_by(syllabus_id=syllabus_id).all()
    job_ids = [j.id for j in jobs]
    package_ids = [p.id for p in packages]

    if job_ids or package_ids:
        conditions = []
        if job_ids:
            conditions.append(MaterialReview.generation_job_id.in_(job_ids))
        if package_ids:
            conditions.append(MaterialReview.package_id.in_(package_ids))
        reviews = MaterialReview.query.filter(db.or_(*conditions)).all()
        for review in reviews:
            db.session.delete(review)

    for job in jobs:
        db.session.delete(job)
    for package in packages:
        db.session.delete(package)

    title = syllabus.title
    db.session.delete(syllabus)
    db.session.commit()

    flash(f"'{title}' and all its generated materials have been deleted.")
    return redirect(url_for("syllabus_web.list_syllabi"))

@syllabus_web_bp.route("/<syllabus_id>/edit", methods=["GET", "POST"])
@login_required
def edit_syllabus(syllabus_id):
    syllabus = Syllabus.query.filter_by(id=syllabus_id, organization_id=current_user.organization_id).first_or_404()
    if current_user.role == "user" and syllabus.created_by_user_id != current_user.id:
        flash("You do not have access to that syllabus.")
        return redirect(url_for("syllabus_web.list_syllabi"))

    if request.method == "POST":
        modules = syllabus.content.get("modules", [])
        updated_modules = []
        for m_idx, module in enumerate(modules):
            # Build a genuinely NEW dict rather than mutating the original in place —
            # mutating the original corrupts SQLAlchemy's internal "before" snapshot for
            # this JSON column (since it's the same object, not a copy), making the old
            # and new values look identical at commit time. That made the save silently
            # do nothing at all, even though the code appeared to succeed.
            new_title = request.form.get(f"module-{m_idx}-title", module.get("title", ""))
            new_module = dict(module)
            new_module["title"] = new_title.strip()

            if module.get("module_type") == "KM":
                topics = module.get("topics", [])
                updated_topics = []
                for t_idx, topic in enumerate(topics):
                    if request.form.get(f"module-{m_idx}-topic-{t_idx}-delete") == "1":
                        continue
                    new_topic_title = request.form.get(f"module-{m_idx}-topic-{t_idx}-title", topic.get("title", ""))
                    new_topic = dict(topic)
                    new_topic["title"] = new_topic_title.strip()
                    updated_topics.append(new_topic)

                new_topic_titles = request.form.getlist(f"module-{m_idx}-new-topic-title[]")
                for new_title in new_topic_titles:
                    if new_title.strip():
                        updated_topics.append({"topic_code": "", "title": new_title.strip(), "elements": []})

                new_module["topics"] = updated_topics

            updated_modules.append(new_module)

        syllabus.content = {**syllabus.content, "modules": updated_modules}
        db.session.commit()
        flash("Syllabus updated successfully.")
        return redirect(url_for("syllabus_web.detail", syllabus_id=syllabus.id))

    return render_template("syllabus/edit.html", syllabus=syllabus)


@syllabus_web_bp.route("/<syllabus_id>/original-file")
@login_required
def view_original_file(syllabus_id):
    from app.services.storage_service import get_presigned_url
    syllabus = Syllabus.query.filter_by(id=syllabus_id, organization_id=current_user.organization_id).first()
    if not syllabus or not syllabus.original_file_key:
        flash("No original file available for this syllabus.")
        return redirect(url_for("syllabus_web.detail", syllabus_id=syllabus_id))

    url = get_presigned_url(syllabus.original_file_key, expires_in=300)
    return redirect(url)
