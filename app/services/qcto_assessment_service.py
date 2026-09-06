"""Builds the QCTO Assessment document for KM or PM modules — cover page, then per-module
assessment sections with questions and blank ruled answer lines, matching the real
Ishida-style assessment format."""
from io import BytesIO
from docx import Document
from docx.shared import Pt, Inches
from app.services.ai_service import generate_qcto_assessment_content
from app.services.document_service import (
    _hex_to_rgb, _build_branded_cover, _add_branded_header_footer, _add_bottom_border,
    DEFAULT_PRIMARY, DEFAULT_SECONDARY,
)

def _add_document_control_and_roles(doc, primary, primary_hex, module_type, qualification_title):
    """Adds a Document Control table and 'A Note on Roles' section, matching the standard
    front-matter of a real QCTO assessment pack. Organization-specific fields (document
    number, version, compiled by, approval, review dates, companion document) are left
    blank for the SDP to fill in manually — these are administrative details specific to
    each provider, not something the system can know or should invent."""
    doc_label = "Knowledge Module Assessment Pack" if module_type == "KM" else "Practical Module Assessment Pack"

    heading = doc.add_paragraph()
    h_run = heading.add_run("Document Control")
    h_run.bold = True
    h_run.font.size = Pt(14)
    h_run.font.color.rgb = primary
    _add_bottom_border(heading, primary_hex)

    control_table = doc.add_table(rows=8, cols=2)
    control_table.style = "Table Grid"
    control_fields = [
        ("Document title", f"{doc_label} \u2014 {qualification_title}"),
        ("Document number", ""),
        ("Version", ""),
        ("Compiled by", ""),
        ("Approved by", ""),
        ("Date of issue", ""),
        ("Next review date", ""),
        ("Companion document", ""),
    ]
    for i, (label, value) in enumerate(control_fields):
        control_table.cell(i, 0).text = label
        control_table.cell(i, 0).paragraphs[0].runs[0].bold = True
        control_table.cell(i, 1).text = value

    doc.add_paragraph()

    roles_heading = doc.add_paragraph()
    rh_run = roles_heading.add_run("A Note on Roles Used in This Pack")
    rh_run.bold = True
    rh_run.font.size = Pt(14)
    rh_run.font.color.rgb = primary
    _add_bottom_border(roles_heading, primary_hex)

    if module_type == "KM":
        roles_text = (
            "Throughout this pack the person who prepares the learner, delivers the knowledge "
            "modules and marks the formative activities is referred to as the SME (Subject Matter "
            "Expert). Where legacy documentation refers to a 'Facilitator', read 'SME'. The final "
            "judgement of competence is made by a registered Assessor and verified by a registered "
            "Internal Moderator."
        )
    else:
        roles_text = (
            "Throughout this pack the person who prepares the learner, delivers the practical "
            "demonstrations, observes workplace performance and marks the formative activities is "
            "referred to as the SME (Subject Matter Expert). Where legacy documentation refers to a "
            "'Facilitator', read 'SME'. The final judgement of competence is made by a registered "
            "Assessor, and verified by a registered Internal Moderator."
        )
    doc.add_paragraph(roles_text)
    doc.add_page_break()

def _add_pack_overview_table(doc, primary, primary_hex, modules, module_type):
    """Adds the 'How This Pack Is Built' overview table, showing the mark allocation
    methodology and a per-module breakdown. Following the standard QCTO convention: each
    module's mark total is its credit value multiplied by ten, applied to both the
    formative and summative components."""
    heading = doc.add_paragraph()
    h_run = heading.add_run("How This Pack Is Built")
    h_run.bold = True
    h_run.font.size = Pt(14)
    h_run.font.color.rgb = primary
    _add_bottom_border(heading, primary_hex)

    component_label = "practical skill" if module_type == "PM" else "knowledge"
    doc.add_paragraph(
        f"The curriculum fixes a percentage weighting for every topic in every {component_label} "
        "module. This pack allocates marks in exactly that proportion. The mark total for each "
        "module is the module's credit value multiplied by ten, split across topics by curriculum "
        "weight, for both the formative and the summative assessment."
    )

    table = doc.add_table(rows=len(modules) + 2, cols=5)
    table.style = "Table Grid"
    headers = ["Module", "Title", "Credits", "Formative", "Summative"]
    for c, h in enumerate(headers):
        table.cell(0, c).text = h
        table.cell(0, c).paragraphs[0].runs[0].bold = True

    total_credits = 0
    total_marks = 0
    for i, module in enumerate(modules, start=1):
        credits = module.get("credits", 0)
        try:
            credits = int(credits)
        except (ValueError, TypeError):
            credits = 0
        marks = credits * 10
        total_credits += credits
        total_marks += marks

        table.cell(i, 0).text = module.get("module_code", "")
        table.cell(i, 1).text = module.get("title", "")
        table.cell(i, 2).text = str(credits)
        table.cell(i, 3).text = str(marks)
        table.cell(i, 4).text = str(marks)

    total_row = len(modules) + 1
    table.cell(total_row, 0).text = "TOTAL"
    table.cell(total_row, 0).paragraphs[0].runs[0].bold = True
    table.cell(total_row, 2).text = str(total_credits)
    table.cell(total_row, 3).text = str(total_marks)
    table.cell(total_row, 4).text = str(total_marks)

    doc.add_paragraph()
    doc.add_page_break()

def _add_part_a1_a2(doc, primary, primary_hex, modules, module_type, organization_name):
    """Adds Part A sections A1 (Learner Details) and A2 (Programme, Provider and
    Role-Player Details), matching the standard structure of a real QCTO assessment pack.
    Delivery weeks and role-player names are left blank — these are specific to each
    provider's actual registered delivery plan and staffing, not something to invent."""
    part_heading = doc.add_paragraph()
    ph_run = part_heading.add_run("PART A — ASSESSMENT ADMINISTRATION")
    ph_run.bold = True
    ph_run.font.size = Pt(16)
    ph_run.font.color.rgb = primary
    _add_bottom_border(part_heading, primary_hex)
    doc.add_paragraph()

    a1_heading = doc.add_paragraph()
    a1_run = a1_heading.add_run("A1  Learner Details")
    a1_run.bold = True
    a1_run.font.size = Pt(13)
    a1_run.font.color.rgb = primary

    a1_fields = [
        "Surname", "Full names", "Learner / student number", "ID number",
        "Home address", "Email address", "Cell number", "Home language",
        "Highest school qualification",
    ]
    a1_table = doc.add_table(rows=len(a1_fields), cols=2)
    a1_table.style = "Table Grid"
    for i, field in enumerate(a1_fields):
        a1_table.cell(i, 0).text = field
        a1_table.cell(i, 0).paragraphs[0].runs[0].bold = True

    doc.add_paragraph()

    a2_heading = doc.add_paragraph()
    a2_run = a2_heading.add_run("A2  Programme, Provider and Role-Player Details")
    a2_run.bold = True
    a2_run.font.size = Pt(13)
    a2_run.font.color.rgb = primary

    sdp_fields = [
        ("Skills Development Provider", organization_name or ""),
        ("Physical address", ""),
        ("Telephone", ""),
        ("Accreditation / SDP number", ""),
    ]
    sdp_table = doc.add_table(rows=len(sdp_fields), cols=2)
    sdp_table.style = "Table Grid"
    for i, (label, value) in enumerate(sdp_fields):
        sdp_table.cell(i, 0).text = label
        sdp_table.cell(i, 0).paragraphs[0].runs[0].bold = True
        sdp_table.cell(i, 1).text = value

    doc.add_paragraph()
    doc.add_paragraph("Role-players").runs[0].bold = True
    roles_table = doc.add_table(rows=5, cols=3)
    roles_table.style = "Table Grid"
    role_headers = ["Role", "Name", "Signature"]
    for c, h in enumerate(role_headers):
        roles_table.cell(0, c).text = h
        roles_table.cell(0, c).paragraphs[0].runs[0].bold = True
    role_names = ["SME (Subject Matter Expert)", "Assessor", "Internal Moderator", "SDP Quality Assurer"]
    for i, name in enumerate(role_names, start=1):
        roles_table.cell(i, 0).text = name

    doc.add_paragraph()
    label = "Knowledge modules" if module_type == "KM" else "Practical skill modules"
    doc.add_paragraph(f"{label} covered by this pack").runs[0].bold = True
    modules_table = doc.add_table(rows=len(modules) + 1, cols=4)
    modules_table.style = "Table Grid"
    mod_headers = ["Curriculum code", f"{label[:-1] if label.endswith('s') else label} title", "Credits", "Delivery weeks"]
    for c, h in enumerate(mod_headers):
        modules_table.cell(0, c).text = h
        modules_table.cell(0, c).paragraphs[0].runs[0].bold = True
    for i, module in enumerate(modules, start=1):
        modules_table.cell(i, 0).text = module.get("module_code", "")
        modules_table.cell(i, 1).text = module.get("title", "")
        modules_table.cell(i, 2).text = str(module.get("credits", ""))
        modules_table.cell(i, 3).text = ""

    doc.add_paragraph()
    doc.add_paragraph(
        "Delivery weeks are taken from the integrated weekly registers. Confirm against the "
        "current register before this pack is issued."
    )
    doc.add_page_break()

def _add_part_a2_1(doc, primary, primary_hex, module_type):
    """Adds Part A2.1 (Provider Programme Accreditation Criteria) as a labeled template
    for the SDP to complete from their actual registered curriculum — physical, human
    resource, and legal accreditation requirements are specific to each qualification's
    registered curriculum and should not be invented."""
    component_label = "knowledge modules" if module_type == "KM" else "practical skill modules"

    heading = doc.add_paragraph()
    h_run = heading.add_run("A2.1  Provider Programme Accreditation Criteria (From the Registered Curriculum)")
    h_run.bold = True
    h_run.font.size = Pt(13)
    h_run.font.color.rgb = primary

    doc.add_paragraph(
        f"These are the conditions the curriculum places on any provider delivering and assessing "
        f"the {component_label}. Complete each section from the qualification's actual registered "
        "curriculum document before this pack is issued."
    )

    for section_title in ["Physical requirements", "Human resource requirements", "Legal requirements"]:
        sub = doc.add_paragraph()
        sub.add_run(section_title).bold = True
        for _ in range(2):
            p = doc.add_paragraph(style="List Bullet")
            p.add_run("_" * 80)

    doc.add_paragraph()
    doc.add_paragraph("Ratio and competence compliance").runs[0].bold = True
    compliance_table = doc.add_table(rows=6, cols=2)
    compliance_table.style = "Table Grid"
    compliance_rows = [
        ("Cohort size", ""),
        ("Trainer to learner ratio required — complies", "Yes  /  No"),
        ("SME meets the required experience/supervisory criteria", "Yes  /  No  —  evidence filed:"),
        ("SME holds the required qualification level", "Yes  /  No  —  evidence filed:"),
        ("Venue/site meets the physical requirements above", "Yes  /  No"),
        ("Provider meets all applicable legal requirements", "Yes  /  No"),
    ]
    for i, (label, value) in enumerate(compliance_rows):
        compliance_table.cell(i, 0).text = label
        compliance_table.cell(i, 1).text = value

    doc.add_paragraph()
    doc.add_page_break()

def _add_part_a3_a4_a5(doc, primary, primary_hex, modules, module_type):
    """Adds Part A sections A3 (Notice to Learner), A4 (Pre-Assessment Plan and
    Schedule), and A5 (Assessment Preparation Form and Declarations) — standard
    procedural sections of a QCTO assessment pack, structurally identical regardless of
    the specific qualification, so built as reusable templates rather than AI-generated."""
    a3_heading = doc.add_paragraph()
    a3_run = a3_heading.add_run("A3  Notice to Learner")
    a3_run.bold = True
    a3_run.font.size = Pt(13)
    a3_run.font.color.rgb = primary

    doc.add_paragraph(
        "All formative activities for a module must be completed and submitted before you are "
        "admitted to that module's summative assessment."
    )

    schedule_table = doc.add_table(rows=len(modules) + 1, cols=4)
    schedule_table.style = "Table Grid"
    headers = ["Module", "Formative due", "Summative date", "Venue"]
    for c, h in enumerate(headers):
        schedule_table.cell(0, c).text = h
        schedule_table.cell(0, c).paragraphs[0].runs[0].bold = True
    for i, module in enumerate(modules, start=1):
        schedule_table.cell(i, 0).text = module.get("module_code", "")

    doc.add_paragraph()
    doc.add_paragraph("What you must bring to the summative assessment:").runs[0].bold = True
    for item in ["Black pen — all learner entries are made in black ink",
                 "Your learner number and ID document",
                 "Any other items specified by your SME for this qualification"]:
        doc.add_paragraph(item, style="List Bullet")

    doc.add_paragraph()
    doc.add_paragraph("Learner\tSignature: ________________\tDate: ________________")
    doc.add_paragraph("SME\tSignature: ________________\tDate: ________________")
    doc.add_paragraph()
    doc.add_page_break()

    a4_heading = doc.add_paragraph()
    a4_run = a4_heading.add_run("A4  Pre-Assessment Plan and Schedule")
    a4_run.bold = True
    a4_run.font.size = Pt(13)
    a4_run.font.color.rgb = primary

    doc.add_paragraph(
        "Agreed between the learner, the SME and the Assessor before assessment begins."
    )

    signoff_table = doc.add_table(rows=3, cols=3)
    signoff_table.style = "Table Grid"
    signoff_rows = ["Candidate details", "Assessor details", "Moderator details"]
    for i, label in enumerate(signoff_rows):
        signoff_table.cell(i, 0).text = label

    doc.add_paragraph()
    component_label = "written knowledge questions" if module_type == "KM" else "direct observation of practical demonstration"
    plan_table = doc.add_table(rows=7, cols=2)
    plan_table.style = "Table Grid"
    plan_rows = [
        ("Assessment methods", component_label),
        ("Assessment instruments", "This assessment pack"),
        ("Evidence to be generated", "Completed formative activities and the summative assessment"),
        ("Weighting", ""),
        ("Sub-minimum", ""),
        ("Re-assessment", ""),
        ("Appeals", ""),
    ]
    for i, (label, value) in enumerate(plan_rows):
        plan_table.cell(i, 0).text = label
        plan_table.cell(i, 0).paragraphs[0].runs[0].bold = True
        plan_table.cell(i, 1).text = value

    doc.add_paragraph()
    doc.add_page_break()

    a5_heading = doc.add_paragraph()
    a5_run = a5_heading.add_run("A5  Assessment Preparation Form and Declarations")
    a5_run.bold = True
    a5_run.font.size = Pt(13)
    a5_run.font.color.rgb = primary

    prep_items = [
        "Explain the purpose of the assessment",
        "Discuss the assessment plan and weightings",
        "Explain the assessment process, instruments and conditions",
        "Identify the role-players",
        "Describe the evidence required to be declared competent",
        "Explain how evidence will be judged",
        "Identify special needs and reasonable accommodation",
    ]
    prep_table = doc.add_table(rows=len(prep_items) + 1, cols=2)
    prep_table.style = "Table Grid"
    prep_table.cell(0, 0).text = "How the learner is prepared"
    prep_table.cell(0, 0).paragraphs[0].runs[0].bold = True
    prep_table.cell(0, 1).text = "Agreed (\u2713)"
    prep_table.cell(0, 1).paragraphs[0].runs[0].bold = True
    for i, item in enumerate(prep_items, start=1):
        prep_table.cell(i, 0).text = item

    doc.add_paragraph()
    doc.add_paragraph(
        "SME declaration: I hereby declare that I have prepared the learner for assessment, that "
        "the learner was consulted, and that all stakeholders have been informed."
    )
    doc.add_paragraph("SME name: ________________\tSignature: ________________\tDate: ________________")
    doc.add_paragraph()
    doc.add_paragraph(
        "Learner declaration: I hereby declare that the SME has prepared me for assessment, that I "
        "was consulted, and that I have been advised of my right to appeal."
    )
    doc.add_paragraph("Learner name: ________________\tSignature: ________________\tDate: ________________")
    doc.add_page_break()

def _add_part_a6_a7(doc, primary, primary_hex, module_type):
    """Adds Part A sections A6 (Assessment Process, Principles and Requirements for
    Competence) and A7 (Appeals, Moderation and Special Needs) — standard QCTO assessment
    principles and process language that applies generically across qualifications,
    rather than content specific to any one curriculum."""
    a6_heading = doc.add_paragraph()
    a6_run = a6_heading.add_run("A6  Assessment Process, Principles and Requirements for Competence")
    a6_run.bold = True
    a6_run.font.size = Pt(13)
    a6_run.font.color.rgb = primary

    doc.add_paragraph("Roles and responsibilities").runs[0].bold = True
    roles_table = doc.add_table(rows=5, cols=2)
    roles_table.style = "Table Grid"
    role_rows = [
        ("SME (Subject Matter Expert)", "Delivers the module; prepares the learner for assessment; marks formative activities; gives continuous feedback and remediation."),
        ("Learner", "Attends, participates, completes all activities honestly and in own words."),
        ("Assessor (registered)", "Makes the final judgement of competence; ensures evidence is valid, authentic, current, sufficient and consistent; records and reports results."),
        ("Internal Moderator (registered)", "Moderates a sample of packs and every Not Yet Competent judgement."),
        ("External Moderator / Verifier", "Conducts external moderation on behalf of the QCTO and the relevant SETA; endorses results before certification."),
    ]
    for i, (role, resp) in enumerate(role_rows):
        roles_table.cell(i, 0).text = role
        roles_table.cell(i, 0).paragraphs[0].runs[0].bold = True
        roles_table.cell(i, 1).text = resp

    doc.add_paragraph()
    doc.add_paragraph("Principles of good assessment").runs[0].bold = True
    principles_table = doc.add_table(rows=7, cols=2)
    principles_table.style = "Table Grid"
    principle_rows = [
        ("Valid", "It measures the content the curriculum states, at the weighting the curriculum sets."),
        ("Authentic", "It is the learner's own work."),
        ("Reliable", "It would produce a consistent result if judged by another assessor."),
        ("Sufficient", "There is enough evidence to cover every internal assessment criterion."),
        ("Current", "It reflects the learner's knowledge and skill now."),
        ("Flexible", "It uses varied question or evidence types appropriate to the content."),
        ("Fair", "It supports learning and takes any special need into account."),
    ]
    for i, (label, desc) in enumerate(principle_rows):
        principles_table.cell(i, 0).text = label
        principles_table.cell(i, 0).paragraphs[0].runs[0].bold = True
        principles_table.cell(i, 1).text = desc

    doc.add_paragraph()
    doc.add_paragraph("Requirements for competence").runs[0].bold = True
    competence_table = doc.add_table(rows=4, cols=3)
    competence_table.style = "Table Grid"
    comp_headers = ["Component", "Sub-minimum", "Weighting toward the module mark"]
    for c, h in enumerate(comp_headers):
        competence_table.cell(0, c).text = h
        competence_table.cell(0, c).paragraphs[0].runs[0].bold = True
    comp_rows = [
        ("Formative activities", "", ""),
        ("Summative assessment", "", ""),
        ("Combined module mark", "", "100%"),
    ]
    for i, (label, sub, weight) in enumerate(comp_rows, start=1):
        competence_table.cell(i, 0).text = label
        competence_table.cell(i, 1).text = sub
        competence_table.cell(i, 2).text = weight

    doc.add_paragraph()
    doc.add_paragraph(
        "All formative activities for a module must be complete before the learner is admitted to "
        "that module's summative assessment."
    )
    doc.add_page_break()

    a7_heading = doc.add_paragraph()
    a7_run = a7_heading.add_run("A7  Appeals, Moderation and Special Needs")
    a7_run.bold = True
    a7_run.font.size = Pt(13)
    a7_run.font.color.rgb = primary

    doc.add_paragraph("Right of appeal").runs[0].bold = True
    doc.add_paragraph(
        "You may appeal against an assessment decision or practice you regard as unfair, invalid, "
        "unreliable, unethical, or made by an assessor without adequate expertise. Appeals are "
        "lodged in writing within the timeframe set by the SDP's assessment policy."
    )

    doc.add_paragraph("Moderation").runs[0].bold = True
    doc.add_paragraph(
        "A sample of assessment packs per cohort is internally moderated by a registered Internal "
        "Moderator, and every Not Yet Competent judgement is moderated. All packs are retained by "
        "the SDP for external moderation and verification."
    )

    doc.add_paragraph("Special needs and reasonable accommodation").runs[0].bold = True
    doc.add_paragraph(
        "If a disability, medical condition, language barrier or other circumstance affects how you "
        "can be assessed, tell your SME during orientation so that reasonable accommodation can be "
        "arranged and recorded on the assessment plan. Accommodation changes how competence is "
        "demonstrated — it never lowers the standard required."
    )

    doc.add_paragraph("Recognition of prior learning").runs[0].bold = True
    doc.add_paragraph(
        "If you already hold credits or can show equivalent knowledge or skill, you may present that "
        "evidence to the Assessor for consideration under RPL. Evidence must still meet the "
        "principles above."
    )
    doc.add_page_break()

def _add_module_alignment_table(doc, primary, primary_hex, module, module_type):
    """Adds the per-module 'Module Alignment' table and topic/activity weighting table
    that precedes that module's actual questions, matching the reference pack structure.
    For KM, uses each topic's real extracted weight percentage where available. For PM,
    no per-item weight is captured by extraction, so marks are split evenly across
    performance assessment items instead of inventing a weighting. In both cases the
    last item absorbs any rounding remainder, so the marks column always sums to exactly
    the module's credit-based total rather than drifting by a mark or two."""
    credits = module.get("credits", 0)
    try:
        credits = int(credits)
    except (ValueError, TypeError):
        credits = 0
    module_total = credits * 10

    component_label = "Knowledge module" if module_type == "KM" else "Practical skill module"
    methods = ("Written knowledge questions, application and scenario questions"
               if module_type == "KM" else
               "Direct observation of practical demonstration, oral questioning, and workplace evidence")

    align_heading = doc.add_paragraph()
    ah_run = align_heading.add_run(f"{module.get('module_code', '')}  —  Module Alignment")
    ah_run.bold = True
    ah_run.font.size = Pt(13)
    ah_run.font.color.rgb = primary

    align_table = doc.add_table(rows=7, cols=2)
    align_table.style = "Table Grid"
    align_rows = [
        (component_label, f"{module.get('module_code', '')}: {module.get('title', '')}"),
        ("Curriculum code", module.get("module_code", "")),
        ("NQF Level / Credits", f"{module.get('nqf_level', '')}  |  {credits}"),
        ("Delivery weeks (per integrated register)", ""),
        ("Assessment methods", methods),
        ("Formative total", f"{module_total} marks"),
        ("Summative total", f"{module_total} marks"),
    ]
    for i, (label, value) in enumerate(align_rows):
        align_table.cell(i, 0).text = label
        align_table.cell(i, 0).paragraphs[0].runs[0].bold = True
        align_table.cell(i, 1).text = str(value)

    doc.add_paragraph()

    if module_type == "KM":
        items = module.get("topics", [])
        item_code_key, item_title_key = "topic_code", "title"
        section_title = "Topic weighting and mark allocation"
        col_header = "Topic"
        intro_text = (
            "The curriculum fixes the weighting of each topic. Marks in this pack are allocated in "
            "exactly that proportion, so the assessment cannot over-test a light topic or "
            "under-test a heavy one."
        )
    else:
        items = module.get("performance_assessment", [])
        item_code_key, item_title_key = "code", "text"
        section_title = "Practical skill weighting and mark allocation"
        col_header = "Practical skill"
        intro_text = "Marks in this pack are split evenly across this module's practical skill activities."

    doc.add_paragraph(section_title).runs[0].bold = True
    doc.add_paragraph(intro_text)

    weight_table = doc.add_table(rows=len(items) + 2, cols=4)
    weight_table.style = "Table Grid"
    w_headers = [col_header, "Title", "Curriculum weight", "Marks (formative and summative each)"]
    for c, h in enumerate(w_headers):
        weight_table.cell(0, c).text = h
        weight_table.cell(0, c).paragraphs[0].runs[0].bold = True

    weight_pcts = []
    for item in items:
        if module_type == "KM" and isinstance(item, dict):
            raw = item.get("weight")
            try:
                weight_pcts.append(float(str(raw).replace("%", "")) if raw else None)
            except (ValueError, TypeError):
                weight_pcts.append(None)
        else:
            weight_pcts.append(None)

    item_marks = []
    if items:
        if module_type == "KM" and any(w for w in weight_pcts):
            for w in weight_pcts[:-1]:
                item_marks.append(round(module_total * (w or 0) / 100))
        else:
            even = module_total // len(items)
            for _ in items[:-1]:
                item_marks.append(even)
        item_marks.append(module_total - sum(item_marks))

    total_weight_pct = sum(w for w in weight_pcts if w) if module_type == "KM" else 0

    for i, item in enumerate(items, start=1):
        item_code = item.get(item_code_key, "") if isinstance(item, dict) else ""
        item_title = item.get(item_title_key, "") if isinstance(item, dict) else str(item)
        w = weight_pcts[i - 1]
        weight_display = f"{w:.0f}%" if w else ""

        weight_table.cell(i, 0).text = item_code
        weight_table.cell(i, 1).text = item_title
        weight_table.cell(i, 2).text = weight_display
        weight_table.cell(i, 3).text = str(item_marks[i - 1])

    if items:
        total_row = len(items) + 1
        weight_table.cell(total_row, 0).text = "TOTAL"
        weight_table.cell(total_row, 0).paragraphs[0].runs[0].bold = True
        weight_table.cell(total_row, 2).text = f"{total_weight_pct:.0f}%" if module_type == "KM" else ""
        weight_table.cell(total_row, 3).text = str(sum(item_marks))

    doc.add_paragraph()


def build_qcto_assessment_docx(title: str, syllabus_content: dict, module_type: str = "KM",
                                organization_name: str = None, logo_bytes: bytes = None,
                                brand_colors: dict = None, accreditation_info: dict = None,
                                job_id: str = None) -> BytesIO:
    accreditation_info = dict(accreditation_info or {})
    if syllabus_content.get("qualification_code"):
        accreditation_info.setdefault("qualification_code", syllabus_content.get("qualification_code"))
    document_label = "KM Formative Assessment" if module_type == "KM" else "PM Assessment (Scenario-Based)"
    brand_colors = brand_colors or {}
    primary_hex = brand_colors.get("primary", DEFAULT_PRIMARY).lstrip("#") if brand_colors.get("primary") else DEFAULT_PRIMARY
    secondary_hex = brand_colors.get("secondary", DEFAULT_SECONDARY).lstrip("#") if brand_colors.get("secondary") else DEFAULT_SECONDARY
    primary = _hex_to_rgb(primary_hex, DEFAULT_PRIMARY)
    secondary = _hex_to_rgb(secondary_hex, DEFAULT_SECONDARY)

    label = "KM Formative Assessment" if module_type == "KM" else "PM Assessment (Scenario-Based)"
    qualification_title = syllabus_content.get("qualification_title", "") or title

    doc = Document()
    _build_branded_cover(doc, qualification_title, label, organization_name, logo_bytes, primary, primary_hex, secondary)

    details_table = doc.add_table(rows=6, cols=2)
    details_table.style = "Table Grid"
    for i, field in enumerate(["Learner Name", "Learner ID Number", "Facilitator Name", "Assessor Name", "Moderator Name", "Date of Submission"]):
        details_table.cell(i, 0).text = field
        details_table.cell(i, 0).paragraphs[0].runs[0].bold = True
    doc.add_page_break()

    _add_document_control_and_roles(doc, primary, primary_hex, module_type, qualification_title)

    modules = [m for m in syllabus_content.get("modules", []) if m.get("module_type") == module_type]

    _add_pack_overview_table(doc, primary, primary_hex, modules, module_type)
    _add_part_a1_a2(doc, primary, primary_hex, modules, module_type, organization_name)
    _add_part_a2_1(doc, primary, primary_hex, module_type)
    _add_part_a3_a4_a5(doc, primary, primary_hex, modules, module_type)
    _add_part_a6_a7(doc, primary, primary_hex, module_type)

    grand_total_marks = 0
    

    for m_index, module in enumerate(modules, start=1):
        module_heading = doc.add_paragraph()
        mh_run = module_heading.add_run(f"Module {m_index} Assessment")
        mh_run.bold = True
        mh_run.font.size = Pt(18)
        mh_run.font.color.rgb = primary
        _add_bottom_border(module_heading, primary_hex)

        subtitle_p = doc.add_paragraph()
        subtitle_p.add_run(module.get("title", "")).italic = True

        _add_module_alignment_table(doc, primary, primary_hex, module, module_type)

        content = module.get("generated_formative_assessment") if module_type == "KM" else None
        if not content:
            content = generate_qcto_assessment_content(module, job_id=job_id)

        module_marks = 0
        q_number = 1
        for section in content.get("sections", []):
            section_heading = doc.add_paragraph()
            sh_run = section_heading.add_run(section.get("section_label", ""))
            sh_run.bold = True
            sh_run.font.size = Pt(13)
            sh_run.font.color.rgb = secondary
            section_heading.paragraph_format.space_before = Pt(14)

            section_marks = sum(q.get("marks", 0) for q in section.get("questions", []))
            module_marks += section_marks

            for q in section.get("questions", []):
                q_para = doc.add_paragraph()
                q_para.paragraph_format.space_before = Pt(10)
                q_para.add_run(f"{q_number}. {q.get('question_text', '')}")
                marks_run = q_para.add_run(f"  ({q.get('marks', 0)})")
                marks_run.italic = True
                marks_run.font.color.rgb = secondary
                q_number += 1

                blank_lines = max(q.get("blank_lines", 3), min(round(q.get("marks", 0) * 0.8), 8))
                for _ in range(blank_lines):
                    line_para = doc.add_paragraph()
                    line_para.paragraph_format.space_after = Pt(8)
                    line_para.add_run("_" * 100)

            section_total_p = doc.add_paragraph()
            section_total_p.add_run(f"Section Total: {section_marks} marks").bold = True

        module_total_p = doc.add_paragraph()
        module_total_run = module_total_p.add_run(f"Module {m_index} Total: {module_marks} marks")
        module_total_run.bold = True
        module_total_run.font.color.rgb = primary
        grand_total_marks += module_marks

        doc.add_page_break()

    results_heading = doc.add_paragraph()
    rh_run = results_heading.add_run("Assessment Results")
    rh_run.bold = True
    rh_run.font.size = Pt(18)
    rh_run.font.color.rgb = primary
    _add_bottom_border(results_heading, primary_hex)

    total_p = doc.add_paragraph()
    total_p.add_run(f"Total Marks Available: {grand_total_marks}").bold = True

    marks_table = doc.add_table(rows=1, cols=2)
    marks_table.style = "Table Grid"
    marks_table.rows[0].cells[0].text = "Marks Achieved"
    marks_table.rows[0].cells[1].text = "Percentage"

    doc.add_paragraph()
    judgement_p = doc.add_paragraph()
    judgement_p.add_run("Judgement:  ☐ Competent    ☐ Not Yet Competent").bold = True

    doc.add_paragraph()
    doc.add_paragraph("Assessor Comments:").runs[0].bold = True
    doc.add_paragraph("_" * 100)

    doc.add_paragraph()
    doc.add_paragraph("Moderator Comments:").runs[0].bold = True
    doc.add_paragraph("_" * 100)

    doc.add_paragraph()
    sig_table = doc.add_table(rows=3, cols=2)
    sig_table.style = "Table Grid"
    for i, sig_label in enumerate(["Facilitator Signature", "Assessor Signature", "Moderator Signature"]):
        sig_table.cell(i, 0).text = sig_label
        sig_table.cell(i, 1).text = "Date"
        sig_table.cell(i, 0).paragraphs[0].runs[0].bold = True
        sig_table.cell(i, 1).paragraphs[0].runs[0].bold = True

    _add_branded_header_footer(doc, logo_bytes=logo_bytes, qualification_name=qualification_title, organization_name=organization_name, primary_hex=primary_hex, accreditation_info=accreditation_info, document_label=document_label)

    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    return buffer


def build_qcto_km_assessment_docx_adapter(title, units, organization_name=None, seta=None,
                                           nqf_level=None, logo_bytes=None, brand_colors=None,
                                           accreditation_info=None, job_id=None, **kwargs):
    syllabus_content = {"modules": units} if isinstance(units, list) else (units or {"modules": []})
    return build_qcto_assessment_docx(
        title=title, syllabus_content=syllabus_content, module_type="KM",
        organization_name=organization_name, logo_bytes=logo_bytes,
        brand_colors=brand_colors, accreditation_info=accreditation_info, job_id=job_id,
    )


def build_qcto_pm_assessment_docx_adapter(title, units, organization_name=None, seta=None,
                                           nqf_level=None, logo_bytes=None, brand_colors=None,
                                           accreditation_info=None, job_id=None, **kwargs):
    syllabus_content = {"modules": units} if isinstance(units, list) else (units or {"modules": []})
    return build_qcto_assessment_docx(
        title=title, syllabus_content=syllabus_content, module_type="PM",
        organization_name=organization_name, logo_bytes=logo_bytes,
        brand_colors=brand_colors, accreditation_info=accreditation_info, job_id=job_id,
    )