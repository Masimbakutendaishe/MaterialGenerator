"""Builds a fill-in-the-blank assessment docx from AI-generated questions across all syllabus units."""
from io import BytesIO
from docx import Document
from docx.shared import Pt, Inches, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from app.services.ai_service import generate_assessment_questions
from app.services.document_service import _add_branded_header_footer

DEFAULT_PRIMARY = "1A5276"


def _hex_to_rgb(hex_str: str, fallback: str) -> RGBColor:
    try:
        return RGBColor.from_string((hex_str or fallback).lstrip("#").upper())
    except (ValueError, TypeError):
        return RGBColor.from_string(fallback)


def build_assessment_docx(title: str, units: list, organization_name: str = None,
                           seta: str = None, nqf_level: str = None, logo_bytes: bytes = None,
                           brand_colors: dict = None, job_id: str = None, doc_label: str = "Assessment") -> BytesIO:
    brand_colors = brand_colors or {}
    primary_hex = brand_colors.get("primary", DEFAULT_PRIMARY).lstrip("#") if brand_colors.get("primary") else DEFAULT_PRIMARY
    primary = _hex_to_rgb(primary_hex, DEFAULT_PRIMARY)

    doc = Document()

    from app.services.document_service import _build_branded_cover
    _build_branded_cover(doc, title, doc_label, organization_name, logo_bytes, primary, primary_hex, RGBColor(0x28, 0x74, 0xA6))

    # Candidate details table with real borders

    # Candidate details block
    for label in ["Name:", "Date:", "Assessor:"]:
        p = doc.add_paragraph()
        run = p.add_run(f"{label} " + "_" * 40)
        run.font.size = Pt(11)

    doc.add_page_break()

    total_marks = 0
    question_number = 1

    for unit in units:
        unit_name = unit.get("name", "Unit")
        outcomes = unit.get("outcomes", [])

        heading = doc.add_paragraph()
        heading_run = heading.add_run(unit_name)
        heading_run.bold = True
        heading_run.font.size = Pt(16)
        heading_run.font.color.rgb = primary

        result = generate_assessment_questions(unit_name, outcomes, course_title=title, seta=seta, nqf_level=nqf_level, job_id=job_id)
        questions = result.get("questions", [])

        for q in questions:
            marks = q.get("marks", 1)
            total_marks += marks

            q_para = doc.add_paragraph()
            q_para.paragraph_format.space_before = Pt(12)
            q_run = q_para.add_run(f"{question_number}. {q.get('text', '')}")
            q_run.font.size = Pt(12)
            marks_run = q_para.add_run(f"  [{marks} mark{'s' if marks != 1 else ''}]")
            marks_run.italic = True
            marks_run.font.size = Pt(10)

            if q.get("type") == "multiple_choice":
                for i, option in enumerate(q.get("options", [])):
                    letter = chr(65 + i)  # A, B, C, D
                    opt_para = doc.add_paragraph()
                    opt_para.paragraph_format.left_indent = Inches(0.4)
                    opt_para.add_run(f"{letter}) {option}")
            else:
                blank_lines = q.get("blank_lines", 2)
                for _ in range(blank_lines):
                    line_para = doc.add_paragraph()
                    line_para.add_run("_" * 80)

            question_number += 1

        doc.add_page_break()

    heading = doc.add_paragraph()
    h_run = heading.add_run("Results")
    h_run.bold = True
    h_run.font.size = Pt(14)
    h_run.font.color.rgb = primary

    results_table = doc.add_table(rows=2, cols=2)
    results_table.style = "Table Grid"
    results_table.cell(0, 0).text = "Total Marks Available"
    results_table.cell(0, 1).text = str(total_marks)
    results_table.cell(1, 0).text = "Marks Achieved"
    results_table.cell(1, 1).text = ""
    for row in results_table.rows:
        row.cells[0].paragraphs[0].runs[0].bold = True

    doc.add_paragraph()
    doc.add_paragraph("Facilitator Comments:").runs[0].bold = True
    for _ in range(3):
        doc.add_paragraph("_" * 90)

    from app.services.document_service import _add_signature_block
    _add_signature_block(doc)

    _add_branded_header_footer(doc, logo_bytes=logo_bytes, qualification_name=title, organization_name=organization_name, primary_hex=primary_hex)

    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    return buffer
