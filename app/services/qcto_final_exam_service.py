"""Builds the QCTO Final Exam — a full multi-format exam paper matching the real BCONSULT-
style reference structure: a header details table, a marks-summary table, then six question
sections (A: Multiple Choice, B: Matching Columns, C: True/False — all AI-generated from
real KM topic/element content via generate_km_exam_objective_questions, since these formats
need genuine authored distractors/pairs/statements, not deterministic templating; D:
Short-Answer built from real KM Internal Assessment Criteria with codes shown explicitly;
E: Practical Scenarios and F: Workplace Recollection, both built from the ISA's real
PM/WM traceability links via reason_isa_traceability, so the exam genuinely follows what
the ISA specifies), followed by a Learner Agreement and Declaration checklist, a Special
Needs section, and Learner Final Assessment Results with Learner/Assessor/Moderator
sign-off."""
from io import BytesIO
from docx import Document
from docx.shared import Pt, Inches, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from app.services.ai_service import reason_isa_traceability, generate_km_exam_objective_questions, generate_km_short_answer_questions, parallel_map
from app.services.document_service import (
    _hex_to_rgb, _build_branded_cover, _add_branded_header_footer, _add_bottom_border,
    DEFAULT_PRIMARY, DEFAULT_SECONDARY,
)

# Marks per question, matching typical accredited exam weighting conventions
MC_MARKS_PER_Q = 2          # 10 questions -> 20 marks
MATCHING_MARKS_PER_PAIR = 2  # 5 pairs -> 10 marks
TF_MARKS_PER_Q = 2          # 10 statements -> 20 marks
THEORY_MARKS, THEORY_MINUTES = 5, 5
SCENARIO_MARKS, SCENARIO_MINUTES = 10, 15
WORKPLACE_MARKS, WORKPLACE_MINUTES = 10, 10


def _section_heading(doc, text, primary, primary_hex, size=18):
    p = doc.add_paragraph()
    run = p.add_run(text)
    run.bold = True
    run.font.size = Pt(size)
    run.font.color.rgb = primary
    _add_bottom_border(p, primary_hex, size="8")
    return p


def _generate_fallback_iac(topic):
    title = topic.get("title", "this topic")
    return [f"Learners can define, describe, and apply the concepts covered in {title}"]


def _add_exam_header_table(doc, primary, primary_hex):
    table = doc.add_table(rows=4, cols=2)
    table.style = "Table Grid"
    for i, field in enumerate(["Training Provider", "Date and Time", "Learner Name and Surname", "Student Number / Identity Number"]):
        table.cell(i, 0).text = field
        table.cell(i, 0).paragraphs[0].runs[0].bold = True
    doc.add_page_break()


def _add_marks_summary_table(doc, section_marks, primary, primary_hex):
    """section_marks: list of (label, marks) tuples for every section in the exam."""
    heading = doc.add_paragraph()
    h_run = heading.add_run("Question Breakdown")
    h_run.bold = True
    h_run.font.size = Pt(16)
    h_run.font.color.rgb = primary
    _add_bottom_border(heading, primary_hex)

    table = doc.add_table(rows=1, cols=3)
    table.style = "Table Grid"
    hdr = table.rows[0].cells
    hdr[0].text, hdr[1].text, hdr[2].text = "Section", "Type", "Marks"
    for c in hdr:
        c.paragraphs[0].runs[0].bold = True

    total = 0
    for i, (label, marks) in enumerate(section_marks, start=1):
        row = table.add_row().cells
        row[0].text = str(i)
        row[1].text = label
        row[2].text = str(marks)
        total += marks

    total_row = table.add_row().cells
    total_row[0].text = ""
    total_row[1].text = "Total Marks"
    total_row[2].text = str(total)
    total_row[1].paragraphs[0].runs[0].bold = True
    total_row[2].paragraphs[0].runs[0].bold = True
    doc.add_page_break()
    return total


def _add_exam_instructions(doc, primary, primary_hex):
    _section_heading(doc, "Instructions to Candidates", primary, primary_hex)
    notice = doc.add_paragraph()
    notice.add_run(
        "This is a formal, individually completed assessment. Read each question carefully "
        "before answering."
    ).bold = True

    for point in [
        "Mark your answers to Section A and Section B on the answer sheets provided.",
        "Answer Sections C through F in your own words in the space provided.",
        "For Practical Scenario questions, address every part of the scenario given.",
        "For Workplace Recollection questions, refer to real examples from your WM Logbook — "
        "generic or hypothetical answers will not be accepted.",
        "Add additional pages if needed, clearly numbered to the correct question.",
    ]:
        doc.add_paragraph(point, style="List Bullet")
    doc.add_page_break()


def _add_multiple_choice_section(doc, mc_questions, primary, primary_hex, secondary):
    _section_heading(doc, "Section A: Multiple Choice", primary, primary_hex)
    doc.add_paragraph(
        "Carefully read each statement and decide which option best answers the question. "
        "Mark your answer on the answer sheet provided after the questions."
    )
    for i, q in enumerate(mc_questions, start=1):
        q_p = doc.add_paragraph()
        q_p.add_run(f"{i}. {q.get('stem', '')}").bold = True
        options = q.get("options", {})
        for letter in ["A", "B", "C", "D", "E"]:
            if letter in options:
                doc.add_paragraph(f"{letter}. {options[letter]}", style="List Bullet")
        doc.add_paragraph()
    doc.add_paragraph(f"Total = {len(mc_questions) * MC_MARKS_PER_Q}").runs[0].bold = True
    doc.add_page_break()

    _section_heading(doc, "Section A — Answer Sheet", primary, primary_hex, size=16)
    table = doc.add_table(rows=1, cols=2)
    table.style = "Table Grid"
    table.rows[0].cells[0].text = "Question"
    table.rows[0].cells[1].text = "Answer (circle one)"
    for c in table.rows[0].cells:
        c.paragraphs[0].runs[0].bold = True
    for i in range(1, len(mc_questions) + 1):
        row = table.add_row().cells
        row[0].text = str(i)
        row[1].text = "A     B     C     D     E"
    doc.add_page_break()


def _add_matching_columns_section(doc, matching_pairs, primary, primary_hex):
    _section_heading(doc, "Section B: Matching Columns", primary, primary_hex)
    doc.add_paragraph(
        "Choose the correct description in Column B for each term in Column A, and write "
        "the matching letter in Column C on the answer sheet provided."
    )

    table = doc.add_table(rows=1, cols=2)
    table.style = "Table Grid"
    table.rows[0].cells[0].text = "Column A (Term)"
    table.rows[0].cells[1].text = "Column B (Description)"
    for c in table.rows[0].cells:
        c.paragraphs[0].runs[0].bold = True

    import random
    shuffled_descriptions = [p.get("description", "") for p in matching_pairs]
    random.shuffle(shuffled_descriptions)

    for pair, shuffled_desc in zip(matching_pairs, shuffled_descriptions):
        row = table.add_row().cells
        row[0].text = pair.get("term", "")
        row[1].text = shuffled_desc

    doc.add_paragraph()
    doc.add_paragraph(f"Total = {len(matching_pairs) * MATCHING_MARKS_PER_PAIR}").runs[0].bold = True
    doc.add_page_break()

    _section_heading(doc, "Section B — Answer Sheet", primary, primary_hex, size=16)
    ans_table = doc.add_table(rows=1, cols=2)
    ans_table.style = "Table Grid"
    ans_table.rows[0].cells[0].text = "Column A (Term)"
    ans_table.rows[0].cells[1].text = "Matching Letter from Column B"
    for c in ans_table.rows[0].cells:
        c.paragraphs[0].runs[0].bold = True
    for pair in matching_pairs:
        row = ans_table.add_row().cells
        row[0].text = pair.get("term", "")
        row[1].text = "_____"
    doc.add_page_break()


def _add_true_false_section(doc, tf_statements, primary, primary_hex):
    _section_heading(doc, "Section C: True or False", primary, primary_hex)
    doc.add_paragraph("Indicate whether each statement is true or false by ticking the relevant column.")

    table = doc.add_table(rows=1, cols=3)
    table.style = "Table Grid"
    hdr = table.rows[0].cells
    hdr[0].text, hdr[1].text, hdr[2].text = "Statement", "True", "False"
    for c in hdr:
        c.paragraphs[0].runs[0].bold = True

    for stmt in tf_statements:
        row = table.add_row().cells
        row[0].text = stmt.get("statement", "")

    doc.add_paragraph()
    doc.add_paragraph(f"Total = {len(tf_statements) * TF_MARKS_PER_Q}").runs[0].bold = True
    doc.add_page_break()


def _add_short_answer_section(doc, km_modules, primary, primary_hex, job_id=None):
    _section_heading(doc, "Section D: Short Answer", primary, primary_hex)
    doc.add_paragraph("Answer the following questions in your own words.")

    topics_to_process = []
    for module in km_modules:
        for topic in module.get("topics", []):
            if topic.get("assessment_criteria") or topic.get("elements"):
                topics_to_process.append(topic)

    # A real time-limited exam samples a representative set of key topics rather than
    # testing every single one exhaustively — without a cap, a large curriculum (many
    # modules, many topics each) produced an impractically long section with an
    # inflated total mark count. Sampling evenly across the full topic list (rather than
    # just taking the first N) ensures later modules are still represented, not just
    # whichever modules happen to come first.
    MAX_SHORT_ANSWER_TOPICS = 10
    if len(topics_to_process) > MAX_SHORT_ANSWER_TOPICS:
        step = len(topics_to_process) / MAX_SHORT_ANSWER_TOPICS
        topics_to_process = [topics_to_process[int(i * step)] for i in range(MAX_SHORT_ANSWER_TOPICS)]

    topic_contents = parallel_map(
        topics_to_process,
        lambda t: generate_km_short_answer_questions(t, job_id=job_id),
        max_workers=3,
    )

    q_number = 1
    total_marks = 0
    for content in topic_contents:
        if content is None:
            continue
        for q in content.get("questions", []):
            q_p = doc.add_paragraph()
            q_run = q_p.add_run(f"{q_number}. {q.get('question_text', '')}")
            q_run.bold = True
            marks_run = q_p.add_run(f"  ({q.get('marks', 0)})")
            marks_run.italic = True
            blank_lines = max(q.get("blank_lines", 4), min(round(q.get("marks", 0) * 0.8), 10))
            for _ in range(blank_lines):
                doc.add_paragraph("_" * 100).paragraph_format.space_after = Pt(6)
            doc.add_paragraph()
            q_number += 1
            total_marks += q.get("marks", 0)

    doc.add_paragraph(f"Total = {total_marks}").runs[0].bold = True
    doc.add_page_break()
    return total_marks


def _add_scenario_and_workplace_sections(doc, km_modules, pm_modules, wm_modules, link_lookup, primary, primary_hex, secondary):
    pm_by_code = {m.get("module_code", ""): m for m in pm_modules}
    wm_by_code = {m.get("module_code", ""): m for m in wm_modules}

    scenario_count = 0
    workplace_count = 0

    _section_heading(doc, "Section E: Practical Scenarios", primary, primary_hex)
    doc.add_paragraph("Respond to each scenario as you would in a real workplace situation.")
    covered_pm_codes = set()
    for module in km_modules:
        for topic in module.get("topics", []):
            link_info = link_lookup.get(topic.get("topic_code", ""), {"pm": [], "wm": []})
            for pm_code in link_info.get("pm", []):
                if pm_code in covered_pm_codes or pm_code not in pm_by_code:
                    continue
                covered_pm_codes.add(pm_code)
                pm_module = pm_by_code[pm_code]
                for pa_raw in pm_module.get("performance_assessment", []):
                    pa_item = pa_raw.get("text", "") if isinstance(pa_raw, dict) else pa_raw
                    scenario_count += 1
                    q_p = doc.add_paragraph()
                    q_p.add_run(
                        f"{scenario_count}. You have been tasked with applying your practical "
                        f"skills in a real workplace context. {pa_item}. Describe, step by "
                        f"step, how you would carry this out."
                    ).bold = True
                    note_p = doc.add_paragraph()
                    note_p.add_run(f"({pm_code}: {pm_module.get('title', '')})").italic = True
                    for _ in range(4):
                        doc.add_paragraph("_" * 100).paragraph_format.space_after = Pt(6)
                    doc.add_paragraph()
    if scenario_count == 0:
        doc.add_paragraph("No Practical Module content was linked via the ISA for this qualification.")
    scenario_marks = scenario_count * SCENARIO_MARKS
    doc.add_paragraph(f"Total = {scenario_marks}").runs[0].bold = True
    doc.add_page_break()

    _section_heading(doc, "Section F: Workplace Recollection", primary, primary_hex)
    doc.add_paragraph(
        "Drawing on your own real experience recorded in your WM Logbook, describe a "
        "specific instance for each question below."
    )
    covered_wm_codes = set()
    for module in km_modules:
        for topic in module.get("topics", []):
            link_info = link_lookup.get(topic.get("topic_code", ""), {"pm": [], "wm": []})
            for wm_code in link_info.get("wm", []):
                if wm_code in covered_wm_codes or wm_code not in wm_by_code:
                    continue
                covered_wm_codes.add(wm_code)
                wm_module = wm_by_code[wm_code]
                for we_item in wm_module.get("work_experience_elements", []):
                    workplace_count += 1
                    q_p = doc.add_paragraph()
                    q_p.add_run(
                        f"{workplace_count}. Referring to your WM Logbook, describe a "
                        f"specific instance where you: {we_item}. Include what the situation "
                        f"was, what you did, and what the outcome was."
                    ).bold = True
                    note_p = doc.add_paragraph()
                    note_p.add_run(f"({wm_code}: {wm_module.get('title', '')})").italic = True
                    for _ in range(4):
                        doc.add_paragraph("_" * 100).paragraph_format.space_after = Pt(6)
                    doc.add_paragraph()
    if workplace_count == 0:
        doc.add_paragraph("No Workplace Module content was linked via the ISA for this qualification.")
    workplace_marks = workplace_count * WORKPLACE_MARKS
    doc.add_paragraph(f"Total = {workplace_marks}").runs[0].bold = True
    doc.add_page_break()

    return scenario_marks, workplace_marks


def _add_marks_achieved_section(doc, section_marks, primary, primary_hex):
    """Fill-in table for the actual marks the learner achieved per section, plus a grand
    total and percentage — filled in by the marker after grading."""
    _section_heading(doc, "Marks Achieved", primary, primary_hex)
    doc.add_paragraph("To be completed by the marker after grading.")

    table = doc.add_table(rows=1, cols=3)
    table.style = "Table Grid"
    hdr = table.rows[0].cells
    hdr[0].text, hdr[1].text, hdr[2].text = "Section", "Marks Available", "Marks Achieved"
    for c in hdr:
        c.paragraphs[0].runs[0].bold = True

    total_available = 0
    for label, marks in section_marks:
        row = table.add_row().cells
        row[0].text = label
        row[1].text = str(marks)
        row[2].text = ""
        total_available += marks

    total_row = table.add_row().cells
    total_row[0].text = "TOTAL"
    total_row[1].text = str(total_available)
    total_row[2].text = ""
    for cell in total_row:
        cell.paragraphs[0].runs[0].bold = True

    doc.add_paragraph()
    doc.add_paragraph("Percentage Achieved: _______ %").runs[0].bold = True

    doc.add_page_break()


def _add_learner_declaration(doc, primary, primary_hex):
    _section_heading(doc, "Learner Agreement and Declaration", primary, primary_hex)

    table = doc.add_table(rows=1, cols=2)
    table.style = "Table Grid"
    table.rows[0].cells[0].text = "Learner Agreement and Declaration"
    table.rows[0].cells[1].text = "Tick"
    for c in table.rows[0].cells:
        c.paragraphs[0].runs[0].bold = True

    for item in [
        "I understand the Appeals Policy to follow if I disagree with the assessor's decision",
        "I had access to an assessment guide that included this assessment",
        "I attended an induction session that I fully understood",
        "I expect to receive feedback from the assessor before further assessment",
        "I accept this assessment as applicable and fair",
        "I know that I can add additional evidence and questions to this assessment",
        "I believe that I am sufficiently prepared to undergo this assessment",
        "I declare that the work contained in this assessment is my own original work",
    ]:
        row = table.add_row().cells
        row[0].text = item

    doc.add_paragraph()
    doc.add_paragraph("Special Needs:").runs[0].bold = True
    for item in ["I have no special needs to be accommodated", "I am ready to continue with this assessment"]:
        doc.add_paragraph(item, style="List Bullet")

    doc.add_paragraph("I have special needs and they are:")
    doc.add_paragraph("_" * 100)
    doc.add_paragraph("_" * 100)
    doc.add_page_break()


def _add_final_results(doc, primary, primary_hex):
    _section_heading(doc, "Learner Final Assessment Results", primary, primary_hex)

    doc.add_paragraph("Assessment Decision:").runs[0].bold = True
    for statement in [
        "The learner has submitted evidence that is valid, relevant, current, sufficient, "
        "and authentic against the specific criteria in which they were declared Competent. "
        "(Yes / No)",
        "The learner is competent in the required areas. (Yes / No)",
    ]:
        doc.add_paragraph(statement, style="List Bullet")

    doc.add_paragraph()
    doc.add_paragraph("The learner is not yet competent in the following areas:").runs[0].bold = True
    doc.add_paragraph("_" * 100)
    doc.add_paragraph("_" * 100)

    doc.add_paragraph()
    doc.add_paragraph("Declaration by Learner").runs[0].bold = True

    sig_table = doc.add_table(rows=3, cols=2)
    sig_table.style = "Table Grid"
    for i, label in enumerate(["Learner's Signature", "Assessor's Signature", "Moderator's Signature"]):
        sig_table.cell(i, 0).text = label
        sig_table.cell(i, 1).text = "Date"
        sig_table.cell(i, 0).paragraphs[0].runs[0].bold = True
        sig_table.cell(i, 1).paragraphs[0].runs[0].bold = True

    doc.add_paragraph()
    footer_note = doc.add_paragraph()
    footer_note_run = footer_note.add_run(
        "The assessment should ensure that all the specific outcomes, critical cross-field "
        "outcomes, and essential embedded knowledge are assessed."
    )
    footer_note_run.italic = True
    footer_note_run.font.size = Pt(9)


def _build_keyword_link_lookup(km_modules, pm_modules, wm_modules):
    def _find_linked(km_topic, candidates):
        km_words = set(w.lower().strip(".,()") for w in km_topic.get("title", "").split() if len(w) > 3)
        linked = []
        for m in candidates:
            m_words = set(w.lower().strip(".,()") for w in m.get("title", "").split() if len(w) > 3)
            if km_words & m_words:
                linked.append(m)
        return linked

    lookup = {}
    for module in km_modules:
        for topic in module.get("topics", []):
            code = topic.get("topic_code", "")
            linked_pm = _find_linked(topic, pm_modules)
            linked_wm = _find_linked(topic, wm_modules)
            lookup[code] = {
                "pm": [m.get("module_code", "") for m in linked_pm],
                "wm": [m.get("module_code", "") for m in linked_wm],
                "reasoning": "",
            }
    return lookup


def build_qcto_final_exam_docx(title: str, syllabus_content: dict, organization_name: str = None,
                                logo_bytes: bytes = None, brand_colors: dict = None,
                                job_id: str = None) -> BytesIO:
    brand_colors = brand_colors or {}
    primary_hex = brand_colors.get("primary", DEFAULT_PRIMARY).lstrip("#") if brand_colors.get("primary") else DEFAULT_PRIMARY
    secondary_hex = brand_colors.get("secondary", DEFAULT_SECONDARY).lstrip("#") if brand_colors.get("secondary") else DEFAULT_SECONDARY
    primary = _hex_to_rgb(primary_hex, DEFAULT_PRIMARY)
    secondary = _hex_to_rgb(secondary_hex, DEFAULT_SECONDARY)
    qualification_title = syllabus_content.get("qualification_title", "") or title

    all_modules = syllabus_content.get("modules", [])
    km_modules = [m for m in all_modules if m.get("module_type") == "KM"]
    pm_modules = [m for m in all_modules if m.get("module_type") == "PM"]
    wm_modules = [m for m in all_modules if m.get("module_type") == "WM"]

    try:
        link_lookup = reason_isa_traceability(km_modules, pm_modules, wm_modules, job_id=job_id)
    except Exception:
        link_lookup = _build_keyword_link_lookup(km_modules, pm_modules, wm_modules)

    try:
        objective_data = generate_km_exam_objective_questions(km_modules, job_id=job_id)
    except Exception:
        objective_data = {"multiple_choice": [], "matching_columns": [], "true_false": []}

    mc_questions = objective_data.get("multiple_choice", [])
    matching_pairs = objective_data.get("matching_columns", [])
    tf_statements = objective_data.get("true_false", [])

    doc = Document()
    _build_branded_cover(doc, qualification_title, "Final Exam", organization_name, logo_bytes, primary, primary_hex, secondary)

    _add_exam_header_table(doc, primary, primary_hex)

    section_marks = [
        ("Multiple Choice", len(mc_questions) * MC_MARKS_PER_Q),
        ("Matching Columns", len(matching_pairs) * MATCHING_MARKS_PER_PAIR),
        ("True or False", len(tf_statements) * TF_MARKS_PER_Q),
    ]
    _add_marks_summary_table(doc, section_marks, primary, primary_hex)

    _add_exam_instructions(doc, primary, primary_hex)
    _add_multiple_choice_section(doc, mc_questions, primary, primary_hex, secondary)
    _add_matching_columns_section(doc, matching_pairs, primary, primary_hex)
    _add_true_false_section(doc, tf_statements, primary, primary_hex)
    short_answer_marks = _add_short_answer_section(doc, km_modules, primary, primary_hex, job_id=job_id)
    scenario_marks, workplace_marks = _add_scenario_and_workplace_sections(doc, km_modules, pm_modules, wm_modules, link_lookup, primary, primary_hex, secondary)

    full_section_marks = section_marks + [
        ("Short Answer", short_answer_marks),
        ("Practical Scenarios", scenario_marks),
        ("Workplace Recollection", workplace_marks),
    ]
    _add_marks_achieved_section(doc, full_section_marks, primary, primary_hex)

    _add_learner_declaration(doc, primary, primary_hex)
    _add_final_results(doc, primary, primary_hex)

    _add_branded_header_footer(doc, logo_bytes=logo_bytes, qualification_name=qualification_title, organization_name=organization_name, primary_hex=primary_hex)

    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    return buffer


def build_qcto_final_exam_docx_adapter(title, units, organization_name=None, seta=None,
                                         nqf_level=None, logo_bytes=None, brand_colors=None,
                                         job_id=None, **kwargs):
    """Adapter matching the standard DOCUMENT_BUILDERS call signature."""
    syllabus_content = {"modules": units} if isinstance(units, list) else (units or {"modules": []})
    return build_qcto_final_exam_docx(
        title=title,
        syllabus_content=syllabus_content,
        organization_name=organization_name,
        logo_bytes=logo_bytes,
        brand_colors=brand_colors,
        job_id=job_id,
    )
