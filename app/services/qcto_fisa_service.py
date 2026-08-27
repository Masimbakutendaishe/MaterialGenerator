"""Builds the QCTO FISA (Final Integrated Summative Assessment) — the single document that
replaces both the ISA (traceability document) and the Final Exam for Skills Programme
qualifications, per spec. Composed by reusing the already-tested section-building functions
from qcto_isa_service.py and qcto_final_exam_service.py rather than duplicating their logic:
the ISA-format traceability table (learner/exam details, intro, per-topic IAC + linked PM/WM
+ performance record) followed by the Final-Exam-format exam paper (header table, marks
summary, instructions, Multiple Choice/Matching/True-False/Short-Answer/Scenario/Workplace
sections, Learner Declaration, and Final Assessment Results). The AI reasoning pass
(reason_isa_traceability) and the objective-question generation (generate_km_exam_objective_
questions) are each called exactly once and shared across both halves of the document,
rather than duplicated. The ISA's own closing sign-off is intentionally omitted in favour of
the Final Exam's more complete Final Assessment Results section, so the combined document
doesn't carry two near-identical Competent/Not-Yet-Competent judgement blocks."""
from io import BytesIO
from docx import Document
from docx.shared import Pt, Inches, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH

from app.services.ai_service import reason_isa_traceability, generate_km_exam_objective_questions
from app.services.document_service import (
    _hex_to_rgb, _build_branded_cover, _add_branded_header_footer,
    DEFAULT_PRIMARY, DEFAULT_SECONDARY,
)

from app.services.qcto_isa_service import (
    _add_isa_learner_details,
    _add_isa_intro,
    _add_isa_traceability_table,
    _build_keyword_link_lookup,
)

from app.services.qcto_final_exam_service import (
    _add_exam_header_table,
    _add_marks_summary_table,
    _add_exam_instructions,
    _add_multiple_choice_section,
    _add_matching_columns_section,
    _add_true_false_section,
    _add_short_answer_section,
    _add_scenario_and_workplace_sections,
    _add_marks_achieved_section,
    _add_learner_declaration,
    _add_final_results,
    MC_MARKS_PER_Q,
    MATCHING_MARKS_PER_PAIR,
    TF_MARKS_PER_Q,
)

def build_qcto_fisa_docx(title: str, syllabus_content: dict, organization_name: str = None,
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

    # Single shared AI reasoning pass — used by both the traceability table and the
    # Practical Scenarios / Workplace Recollection exam sections, not called twice.
    ai_reasoning_used = True
    try:
        link_lookup = reason_isa_traceability(km_modules, pm_modules, wm_modules, job_id=job_id)
    except Exception:
        ai_reasoning_used = False
        link_lookup = _build_keyword_link_lookup(km_modules, pm_modules, wm_modules)

    try:
        objective_data = generate_km_exam_objective_questions(km_modules, job_id=job_id)
    except Exception:
        objective_data = {"multiple_choice": [], "matching_columns": [], "true_false": []}

    mc_questions = objective_data.get("multiple_choice", [])
    matching_pairs = objective_data.get("matching_columns", [])
    tf_statements = objective_data.get("true_false", [])

    doc = Document()
    _build_branded_cover(
        doc, qualification_title, "FISA — Final Integrated Summative Assessment",
        organization_name, logo_bytes, primary, primary_hex, secondary,
    )

    # --- ISA-format traceability half ---
    _add_isa_learner_details(doc, primary, primary_hex)
    _add_isa_intro(doc, primary, primary_hex, ai_reasoning_used)
    _add_isa_traceability_table(doc, km_modules, pm_modules, wm_modules, link_lookup, primary, primary_hex, secondary)

    # --- Final-Exam-format exam paper half ---
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


def build_qcto_fisa_docx_adapter(title, units, organization_name=None, seta=None,
                                   nqf_level=None, logo_bytes=None, brand_colors=None,
                                   job_id=None, **kwargs):
    """Adapter matching the standard DOCUMENT_BUILDERS call signature."""
    syllabus_content = {"modules": units} if isinstance(units, list) else (units or {"modules": []})
    return build_qcto_fisa_docx(
        title=title,
        syllabus_content=syllabus_content,
        organization_name=organization_name,
        logo_bytes=logo_bytes,
        brand_colors=brand_colors,
        job_id=job_id,
    )
