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


def build_qcto_assessment_docx(title: str, syllabus_content: dict, module_type: str = "KM",
                                organization_name: str = None, logo_bytes: bytes = None,
                                brand_colors: dict = None, job_id: str = None) -> BytesIO:
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

    modules = [m for m in syllabus_content.get("modules", []) if m.get("module_type") == module_type]

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

                blank_lines = min(q.get("blank_lines", 3), 6)
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

    _add_branded_header_footer(doc, logo_bytes=logo_bytes, qualification_name=qualification_title, organization_name=organization_name, primary_hex=primary_hex)

    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    return buffer


def build_qcto_km_assessment_docx_adapter(title, units, organization_name=None, seta=None,
                                           nqf_level=None, logo_bytes=None, brand_colors=None,
                                           job_id=None, **kwargs):
    syllabus_content = {"modules": units} if isinstance(units, list) else (units or {"modules": []})
    return build_qcto_assessment_docx(
        title=title, syllabus_content=syllabus_content, module_type="KM",
        organization_name=organization_name, logo_bytes=logo_bytes,
        brand_colors=brand_colors, job_id=job_id,
    )


def build_qcto_pm_assessment_docx_adapter(title, units, organization_name=None, seta=None,
                                           nqf_level=None, logo_bytes=None, brand_colors=None,
                                           job_id=None, **kwargs):
    syllabus_content = {"modules": units} if isinstance(units, list) else (units or {"modules": []})
    return build_qcto_assessment_docx(
        title=title, syllabus_content=syllabus_content, module_type="PM",
        organization_name=organization_name, logo_bytes=logo_bytes,
        brand_colors=brand_colors, job_id=job_id,
    )
