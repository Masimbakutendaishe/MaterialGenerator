"""Builds the QCTO PM Assessment Guide — combines the KM Assessment Guide's assessor-policy
backbone (4-step process, role-players, principles, evidence, methods) reframed for
practical/scenario-based evidence rather than knowledge questions, with a genuinely new
scenario-based practical activity workbook structure: an 'About This Practical Skills
Module' intro per module, a fillable Learner Information table, a scenario followed by
PA-coded practical activities and IAC-coded assessment criteria drawn from the real PM
module data (performance_assessment / assessment_criteria — not a fabricated nested code
structure we don't have data for), Observation Sheets for peer/assessor sign-off, and
Assessment Feedback + Remediation Feedback + Declaration sections — matching the real
BCONSULT-style reference. Cross-references the real PM document names ("PM Learner Guide",
"PM Facilitator Guide", "PM Assessment (Scenario-Based)")."""
from io import BytesIO
from docx import Document
from docx.shared import Pt, Inches, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from app.services.ai_service import generate_pm_scenario_and_questions, parallel_map
from app.services.document_service import (
    _hex_to_rgb, _build_branded_cover, _add_branded_header_footer, _add_bottom_border,
    _add_toc_field, DEFAULT_PRIMARY, DEFAULT_SECONDARY,
)


def _section_heading(doc, text, primary, primary_hex, size=18):
    p = doc.add_paragraph()
    run = p.add_run(text)
    run.bold = True
    run.font.size = Pt(size)
    run.font.color.rgb = primary
    p.style = doc.styles["Heading 1"]
    _add_bottom_border(p, primary_hex, size="8")
    return p


def _add_pag_cover_details(doc, qualification_title, primary, primary_hex):
    doc.add_paragraph(qualification_title).runs[0].bold = True
    table = doc.add_table(rows=4, cols=2)
    table.style = "Table Grid"
    for i, field in enumerate(["Learner Full Name & Surname", "ID Number", "Assessor", "Date"]):
        table.cell(i, 0).text = field
        table.cell(i, 0).paragraphs[0].runs[0].bold = True
    doc.add_page_break()


def _add_pag_toc(doc, primary, primary_hex, module_count):
    _section_heading(doc, "Table of Contents", primary, primary_hex)
    _add_toc_field(doc)
    doc.add_page_break()


def _add_pag_foreword(doc, primary, primary_hex):
    _section_heading(doc, "Foreword to the Assessor", primary, primary_hex)
    doc.add_paragraph(
        "The purpose of this guide is to provide the Assessor with guidelines on the "
        "assessment of the Practical Portfolio of Evidence submitted by the candidate "
        "(learner) for assessment purposes. Practical modules are assessed primarily on "
        "whether the learner can actually perform the required skill to standard, observed "
        "directly against a realistic workplace scenario — not on written recall alone."
    )
    doc.add_paragraph(
        "Formative assessment refers to assessment that takes place during the process of "
        "learning and teaching, through supervised practice. Summative assessment is "
        "assessment for making a judgement about achievement, carried out through direct "
        "observation of a practical demonstration once the learner is ready."
    )
    doc.add_page_break()


def _add_pag_process_and_steps(doc, primary, primary_hex, secondary):
    _section_heading(doc, "Assessment Process", primary, primary_hex)
    for i, step in enumerate([
        "Plan & prepare for assessment",
        "Conduct & record the assessment",
        "Provide feedback on the assessment",
        "Review and report on the assessment",
    ], start=1):
        doc.add_paragraph(f"Step {i}: {step}", style="List Number")
    doc.add_page_break()

    _section_heading(doc, "Assessment Steps", primary, primary_hex)

    pm_learner_guide = "PM Learner Guide"
    pm_facilitator_guide = "PM Facilitator Guide"
    pm_scenario_assessment = "PM Assessment (Scenario-Based)"

    steps = [
        (
            "Step 1: Plan and Prepare for the Assessment",
            [
                "Understand and review the practical evidence required to prove competence for each scenario.",
                "Identify logistical arrangements — venue, equipment, materials, and safety provisions.",
                f"Familiarise themselves with the {pm_facilitator_guide} and the scenario-based assessment instruments.",
                "Ensure familiarity with the related Assessment, Moderation, RPL, and Appeals policies.",
            ],
            [
                f"Be guided in preparing for assessment using the {pm_learner_guide} and {pm_scenario_assessment}.",
                "Be informed of the practical scenario(s) they will be assessed against and what evidence is required.",
                "Have any assessment process related questions answered.",
            ],
            f"{pm_learner_guide}, {pm_scenario_assessment}, {pm_facilitator_guide}",
        ),
        (
            "Step 2: Conduct and Record the Assessment",
            [
                "Observe the learner performing the practical activity directly against the scenario, applying the assessment principles.",
                f"Complete the Observation Sheet for each practical activity, referring to the {pm_facilitator_guide}'s Marking Memorandum for guidance.",
                "Make a judgement about the evidence against the internal assessment criteria (IAC) for each activity.",
                "Record the assessment findings on the Observation Sheet and Assessment Feedback documents.",
            ],
            [
                f"Perform each practical activity in the {pm_scenario_assessment} according to the scenario provided.",
            ],
            "Observation Sheets, Assessment Feedback document",
        ),
        (
            "Step 3: Provide Assessment Feedback to the Learner",
            [
                "Provide the learner with feedback in both a positive and constructive manner.",
                "Advise the learner of any outstanding or required evidence.",
            ],
            [
                "Confirm receipt, understanding, and acceptance of the feedback via the Declaration by Learner.",
            ],
            "Assessment Feedback document",
        ),
        (
            "Step 4: Review and Report the Assessment",
            [
                "Review the assessment process and report the outcome (Competent / Not Yet Competent).",
                "Where NYC, arrange remediation and re-assessment on the specific criteria not yet met.",
            ],
            [
                "Where re-assessed, keep the original assessment record in the Portfolio of Evidence alongside the remediation record.",
            ],
            "Remediation: Assessment Feedback document",
        ),
    ]

    for title, assessor_items, learner_items, documents in steps:
        step_heading = doc.add_paragraph()
        step_heading.add_run(title).bold = True
        step_heading.runs[0].font.size = Pt(14)
        step_heading.runs[0].font.color.rgb = secondary

        doc.add_paragraph("Assessor needs to:").runs[0].bold = True
        for item in assessor_items:
            doc.add_paragraph(item, style="List Bullet")

        doc.add_paragraph("Learner needs to:").runs[0].bold = True
        for item in learner_items:
            doc.add_paragraph(item, style="List Bullet")

        doc.add_paragraph(f"Documents: {documents}").runs[0].italic = True
        doc.add_paragraph()

    doc.add_page_break()


def _add_pag_role_players(doc, primary, primary_hex, secondary):
    _section_heading(doc, "The Assessment Process Role-Players", primary, primary_hex)

    learner_heading = doc.add_paragraph()
    learner_heading.add_run("Learner").bold = True
    learner_heading.runs[0].font.color.rgb = secondary
    doc.add_paragraph(
        "The learner performs each practical activity against the scenario provided, using "
        "the PM Assessment (Scenario-Based) instrument, and is observed directly by the "
        "assessor or assessed by another learner using the Observation Sheet where peer "
        "assessment is used."
    )

    facilitator_heading = doc.add_paragraph()
    facilitator_heading.add_run("Facilitator").bold = True
    facilitator_heading.runs[0].font.color.rgb = secondary
    doc.add_paragraph(
        "The facilitator prepares the learner through demonstration and guided practice, "
        "using the PM Learner Guide and PM Facilitator Guide, before the learner attempts "
        "independent, assessed performance of the practical activity."
    )
    doc.add_page_break()


def _add_pag_principles(doc, primary, primary_hex):
    _section_heading(doc, "Principles of Assessment", primary, primary_hex)
    table = doc.add_table(rows=1, cols=2)
    table.style = "Table Grid"
    table.rows[0].cells[0].text = "Principle"
    table.rows[0].cells[1].text = "Description"
    for c in table.rows[0].cells:
        c.paragraphs[0].runs[0].bold = True

    principles = [
        ("Valid", "The assessment focuses on the requirements laid down in the standard — it is fit for purpose."),
        ("Authentic", "The assessor is satisfied that the practical work observed is genuinely performed by the person being assessed."),
        ("Current", "The evidence must demonstrate that the person's practical competence is current."),
        ("Sufficient", "The evidence establishes that all criteria are met and performance can be repeated consistently."),
        ("Fair", "The scenario chosen must be fair and must not present barriers unrelated to the practical skill."),
        ("Direct", "Observing the learner perform the actual skill mirrors real performance as closely as possible."),
        ("Consistent", "The same assessor makes the same judgement about the same performance under similar circumstances."),
    ]
    for name, desc in principles:
        row = table.add_row().cells
        row[0].text, row[1].text = name, desc
    doc.add_page_break()


def _add_pag_evidence_and_methods(doc, primary, primary_hex):
    _section_heading(doc, "Assessing Evidence", primary, primary_hex)
    doc.add_paragraph(
        "For practical modules, evidence is judged primarily through direct observation — "
        "watching the learner perform the practical activity against the scenario — "
        "supplemented by any physical outputs produced (completed templates, documents, "
        "or work samples)."
    )

    doc.add_paragraph()
    _section_heading(doc, "Assessment Methods", primary, primary_hex, size=16)
    table = doc.add_table(rows=1, cols=2)
    table.style = "Table Grid"
    table.rows[0].cells[0].text = "Method"
    table.rows[0].cells[1].text = "Description"
    for c in table.rows[0].cells:
        c.paragraphs[0].runs[0].bold = True

    methods = [
        ("Scenario-Based Practical Demonstration", "The learner performs the practical activity in response to a realistic workplace scenario, observed directly by the assessor."),
        ("Observation", "The assessor records what they observe against each internal assessment criterion on the Observation Sheet."),
        ("Product Evaluation", "Physical outputs produced during the activity (templates, documents, plans) are evaluated against the required standard."),
        ("Peer Assessment", "Other learners assess a role-player's performance using the same Observation Sheet, developing their own evaluative judgement."),
    ]
    for name, desc in methods:
        row = table.add_row().cells
        row[0].text, row[1].text = name, desc
    doc.add_page_break()


def _add_pag_learner_information(doc, primary, primary_hex):
    _section_heading(doc, "Learner Information", primary, primary_hex)
    table = doc.add_table(rows=1, cols=2)
    table.style = "Table Grid"
    table.rows[0].cells[0].text = "Details"
    table.rows[0].cells[1].text = "Please Complete Details"
    for c in table.rows[0].cells:
        c.paragraphs[0].runs[0].bold = True

    for field in ["Candidate Name", "Candidate ID Number", "Name of Manager",
                  "Work Unit / Department", "Facilitator", "Date Started", "Date of Completion"]:
        row = table.add_row().cells
        row[0].text = field
    doc.add_page_break()


def _add_pag_module_intro(doc, module, module_index, primary, primary_hex):
    """'About This Practical Skills Module' — data-driven from real performance_assessment
    items, matching the reference's compulsory-activity notice + PS-coded requirement list."""
    _section_heading(doc, f"About This Practical Skills Module {module_index}: {module.get('title', '')}", primary, primary_hex)

    notice = doc.add_paragraph()
    notice.add_run(
        "The activities in this workbook are compulsory. You must complete them in class and "
        "they will be marked by your facilitator. These activities must then be stored in "
        "your Portfolio of Evidence and submitted for assessment."
    ).bold = True

    doc.add_paragraph("Purpose of the Practical Skill Module:").runs[0].bold = True
    doc.add_paragraph(
        f"The focus of the learning in this module is on providing the learner an opportunity "
        f"to practise: {module.get('title', '')}."
    )

    pa_items = [p.get("text", "") if isinstance(p, dict) else p for p in (module.get("performance_assessment") or [])]
    module_code = module.get("module_code", "")
    if pa_items:
        doc.add_paragraph("The learner will be required to:").runs[0].bold = True
        for i, item in enumerate(pa_items, start=1):
            doc.add_paragraph(f"{module_code}-PS{i:02d}: {item}", style="List Bullet")

    doc.add_paragraph()
    doc.add_paragraph("Important Points to Remember:").runs[0].bold = True
    for point in [
        "Complete the activities in your own words — do not copy from your learning guide.",
        "Please write legibly.",
        "Answer the questions in the space provided.",
        "Add additional pages if there is not enough space, and number them clearly to the correct activity.",
    ]:
        doc.add_paragraph(point, style="List Bullet")

    doc.add_paragraph()
    doc.add_paragraph("Requirements:").runs[0].bold = True
    for item in [
        "Learning resources that are aligned to the content of this module",
        "Assessment instruments that are focused on the internal assessment criteria",
        "Access to training facilities that are well equipped and conducive for effective learning",
    ]:
        doc.add_paragraph(item, style="List Bullet")

    doc.add_paragraph("Human Resource Requirements:").runs[0].bold = True
    for item in [
        "Facilitators of learning with subject matter expertise as covered by this module",
        "Facilitators who have achieved a nationally accepted standard in the delivery of occupational learning",
        "Facilitators of learning who have achieved a recognised learning standard in assessment practice",
    ]:
        doc.add_paragraph(item, style="List Bullet")
    doc.add_page_break()


def _add_observation_sheet(doc, primary, primary_hex, item_label):
    doc.add_paragraph("Every learner is to assess the role-player's performance using the observation sheet below.")

    table = doc.add_table(rows=1, cols=4)
    table.style = "Table Grid"
    hdr = table.rows[0].cells
    hdr[0].text, hdr[1].text, hdr[2].text, hdr[3].text = "Did the learner:", "Yes", "No", "Comments"
    for c in hdr:
        c.paragraphs[0].runs[0].bold = True
    row = table.add_row().cells
    row[0].text = item_label

    doc.add_paragraph()
    obs_p = doc.add_paragraph()
    obs_p.add_run("Observed by: ").bold = True
    obs_p.add_run("_" * 40)
    judgement_p = doc.add_paragraph()
    judgement_p.add_run("Judgement:  ☐ Competent (C)    ☐ Not Yet Competent (NYC)").bold = True
    doc.add_paragraph()


def _add_pag_scenario_and_activities(doc, module, module_index, primary, primary_hex, secondary, group_contents=None):
    """Scenario followed by PA-coded practical activities and IAC-coded assessment
    criteria — PA items are grouped (a few at a time) with ONE consolidated,
    AI-generated South African scenario and question set per group, rather than a full
    scenario+question block per individual skill, which for modules with many skills was
    producing an impractically long document. IAC criteria are shown once for the whole
    module rather than repeated per item. Observation sheets stay one per individual
    skill, since genuine competent/not-yet-competent assessment needs that granularity.
    group_contents is pre-fetched by the caller (across the whole document, concurrently)
    rather than generated here, so this function stays purely a renderer."""
    _section_heading(doc, f"Scenario and Practical Applied Activities — Module {module_index}: {module.get('title', '')}", primary, primary_hex)

    module_code = module.get("module_code", "")
    pa_items = module.get("performance_assessment") or []
    iac_items = module.get("assessment_criteria") or []

    if pa_items and group_contents:
        doc.add_paragraph(
            "The learner is to use the scenarios below when completing the Practical "
            "Activities of this module."
        )
        doc.add_paragraph()

        if iac_items:
            doc.add_paragraph("Internal Assessment Criteria — the Assessor is to ensure the learner has demonstrated:").runs[0].bold = True
            for j, criterion in enumerate(iac_items, start=1):
                doc.add_paragraph(f"IAC{j:02d} {criterion}", style="List Bullet")
            doc.add_paragraph()

        group_size = 4
        groups = [pa_items[i:i + group_size] for i in range(0, len(pa_items), group_size)]
        item_counter = 1

        for group, content in zip(groups, group_contents):
            if content is None:
                item_counter += len(group)
                continue

            applied_heading = doc.add_paragraph()
            applied_heading.add_run("Practical Applied").bold = True
            applied_heading.runs[0].font.color.rgb = secondary

            scenario_p = doc.add_paragraph()
            scenario_run = scenario_p.add_run(f"SCENARIO: {content.get('scenario', '')}")
            scenario_run.bold = True
            doc.add_paragraph()

            doc.add_paragraph("Answer the following, in the context of the scenario above:").runs[0].italic = True
            for q_num, question in enumerate(content.get("questions", []), start=1):
                q_p = doc.add_paragraph()
                q_p.add_run(f"{q_num}. {question}")
                for _ in range(3):
                    doc.add_paragraph("_" * 100)

            doc.add_paragraph()
            for pa in group:
                text = pa.get("text", "") if isinstance(pa, dict) else (pa or "")
                _add_observation_sheet(doc, primary, primary_hex, f"{module_code}-PS{item_counter:02d}: {text}")
                item_counter += 1
            doc.add_paragraph()
    else:
        doc.add_paragraph(
            f"No specific practical skills were extracted for {module.get('title', '')} — "
            f"review the source curriculum for this module before assessing."
        ).runs[0].italic = True

    doc.add_page_break()


def _add_pag_assessment_feedback(doc, primary, primary_hex, remediation=False):
    heading_text = "Remediation: Assessment Feedback" if remediation else "Assessment Feedback"
    _section_heading(doc, heading_text, primary, primary_hex)

    table = doc.add_table(rows=3, cols=4)
    table.style = "Table Grid"
    fields = [
        ("Candidate Name", "Candidate ID Nr"),
        ("Assessor Name", "Assessor Nr"),
        ("Moderator Name", "Moderator Nr"),
    ]
    for i, (left, right) in enumerate(fields):
        table.cell(i, 0).text = left
        table.cell(i, 2).text = right
        table.cell(i, 0).paragraphs[0].runs[0].bold = True
        table.cell(i, 2).paragraphs[0].runs[0].bold = True

    doc.add_paragraph()
    judgement_p = doc.add_paragraph()
    judgement_p.add_run("Judgement:  ☐ Competent (C)    ☐ Not Yet Competent (NYC)").bold = True

    doc.add_paragraph()
    doc.add_paragraph("Comments from Learner:").runs[0].bold = True
    doc.add_paragraph("_" * 100)
    doc.add_paragraph()

    doc.add_paragraph("Assessor Feedback Remarks:").runs[0].bold = True
    doc.add_paragraph("_" * 100)
    doc.add_paragraph()

    doc.add_paragraph("Declaration by Learner:").runs[0].bold = True
    doc.add_paragraph(
        "I, " + "_" * 40 + ", declare that I am satisfied that the feedback given to me by "
        "the Assessor was relevant, sufficient, and done in a constructive manner. I accept "
        "the assessment judgment and have no further questions relating to this particular "
        "assessment."
    )

    sig_table = doc.add_table(rows=3, cols=2)
    sig_table.style = "Table Grid"
    for i, label in enumerate(["Learner Signature", "Assessor Signature", "Moderator Signature"]):
        sig_table.cell(i, 0).text = label
        sig_table.cell(i, 1).text = "Date"
        sig_table.cell(i, 0).paragraphs[0].runs[0].bold = True
        sig_table.cell(i, 1).paragraphs[0].runs[0].bold = True
    doc.add_page_break()


def build_qcto_pm_assessment_guide_docx(title: str, syllabus_content: dict, organization_name: str = None,
                                         logo_bytes: bytes = None, brand_colors: dict = None,
                                         accreditation_info: dict = None, job_id: str = None) -> BytesIO:
    accreditation_info = dict(accreditation_info or {})
    if syllabus_content.get("qualification_code"):
        accreditation_info.setdefault("qualification_code", syllabus_content.get("qualification_code"))
    brand_colors = brand_colors or {}
    primary_hex = brand_colors.get("primary", DEFAULT_PRIMARY).lstrip("#") if brand_colors.get("primary") else DEFAULT_PRIMARY
    secondary_hex = brand_colors.get("secondary", DEFAULT_SECONDARY).lstrip("#") if brand_colors.get("secondary") else DEFAULT_SECONDARY
    primary = _hex_to_rgb(primary_hex, DEFAULT_PRIMARY)
    secondary = _hex_to_rgb(secondary_hex, DEFAULT_SECONDARY)
    qualification_title = syllabus_content.get("qualification_title", "") or title

    pm_modules = [m for m in syllabus_content.get("modules", []) if m.get("module_type") == "PM"]

    doc = Document()
    _build_branded_cover(doc, qualification_title, "PM Assessment Guide", organization_name, logo_bytes, primary, primary_hex, secondary)

    _add_pag_cover_details(doc, qualification_title, primary, primary_hex)
    _add_pag_toc(doc, primary, primary_hex, module_count=len(pm_modules) or 1)
    _add_pag_foreword(doc, primary, primary_hex)
    _add_pag_process_and_steps(doc, primary, primary_hex, secondary)
    _add_pag_role_players(doc, primary, primary_hex, secondary)
    _add_pag_principles(doc, primary, primary_hex)
    _add_pag_evidence_and_methods(doc, primary, primary_hex)
    _add_pag_learner_information(doc, primary, primary_hex)

    # Use the already-cached scenario/questions groups if the task layer generated them
    # (shared with PM POE, so both documents show identical scenarios) — only fetch fresh
    # for modules that don't have cached content yet (e.g. this builder called outside
    # the normal task-layer path).
    per_module_results = []
    tasks_needing_fetch = []
    task_positions = []  # (module_index_in_pm_modules) for each task, to slot results back in
    for m_idx, module in enumerate(pm_modules):
        cached = module.get("generated_pm_scenario_groups")
        if cached:
            per_module_results.append(cached)
            continue

        pa_items = module.get("performance_assessment") or []
        group_size = 4
        groups = [pa_items[i:i + group_size] for i in range(0, len(pa_items), group_size)]
        per_module_results.append(None)  # placeholder, filled in after the fetch below
        for group in groups:
            tasks_needing_fetch.append((module, group))
            task_positions.append(m_idx)

    if tasks_needing_fetch:
        fetched = parallel_map(
            tasks_needing_fetch,
            lambda t: generate_pm_scenario_and_questions(t[0].get("title", ""), t[1], job_id=job_id),
            max_workers=3,
        )
        # Regroup fetched results back onto their originating module's placeholder slot.
        grouped_by_module = {}
        for pos, result in zip(task_positions, fetched):
            grouped_by_module.setdefault(pos, []).append(result)
        for m_idx, results in grouped_by_module.items():
            per_module_results[m_idx] = results

    for i, module in enumerate(pm_modules, start=1):
        _add_pag_module_intro(doc, module, i, primary, primary_hex)
        _add_pag_scenario_and_activities(doc, module, i, primary, primary_hex, secondary, group_contents=per_module_results[i - 1])

    _add_pag_assessment_feedback(doc, primary, primary_hex, remediation=False)
    _add_pag_assessment_feedback(doc, primary, primary_hex, remediation=True)

    _add_branded_header_footer(doc, logo_bytes=logo_bytes, qualification_name=qualification_title, organization_name=organization_name, primary_hex=primary_hex, accreditation_info=accreditation_info, document_label="PM Assessment Guide")

    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    return buffer


def build_qcto_pm_assessment_guide_docx_adapter(title, units, organization_name=None, seta=None,
                                                  nqf_level=None, logo_bytes=None, brand_colors=None,
                                                  accreditation_info=None, job_id=None, **kwargs):
    """Adapter matching the standard DOCUMENT_BUILDERS call signature."""
    syllabus_content = {"modules": units} if isinstance(units, list) else (units or {"modules": []})
    return build_qcto_pm_assessment_guide_docx(
        title=title,
        syllabus_content=syllabus_content,
        organization_name=organization_name,
        logo_bytes=logo_bytes,
        brand_colors=brand_colors,
        accreditation_info=accreditation_info,
        job_id=job_id,
    )
