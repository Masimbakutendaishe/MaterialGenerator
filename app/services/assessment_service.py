"""Builds a fill-in-the-blank assessment docx from AI-generated questions across all syllabus units."""
from io import BytesIO
from docx import Document
from docx.shared import Pt, Inches, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from app.services.ai_service import generate_assessment_questions

DEFAULT_PRIMARY = "1A5276"


def _hex_to_rgb(hex_str: str, fallback: str) -> RGBColor:
    try:
        return RGBColor.from_string((hex_str or fallback).lstrip("#").upper())
    except (ValueError, TypeError):
        return RGBColor.from_string(fallback)


def build_assessment_docx(title: str, units: list, organization_name: str = None,
                           seta: str = None, nqf_level: str = None, logo_bytes: bytes = None,
                           brand_colors: dict = None) -> BytesIO:
    brand_colors = brand_colors or {}
    primary = _hex_to_rgb(brand_colors.get("primary"), DEFAULT_PRIMARY)

    doc = Document()

    if logo_bytes:
        logo_para = doc.add_paragraph()
        logo_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = logo_para.add_run()
        run.add_picture(BytesIO(logo_bytes), width=Inches(1.3))

    title_para = doc.add_paragraph()
    title_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title_run = title_para.add_run(f"{title} — Assessment")
    title_run.bold = True
    title_run.font.size = Pt(24)
    title_run.font.color.rgb = primary

    if organization_name:
        sub = doc.add_paragraph()
        sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
        sub_run = sub.add_run(organization_name)
        sub_run.font.size = Pt(12)

    doc.add_paragraph()

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

        result = generate_assessment_questions(unit_name, outcomes, seta=seta, nqf_level=nqf_level)
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
    total_para = doc.add_paragraph()
    total_run = total_para.add_run(f"Total Marks: {total_marks}")
    total_run.bold = True
    total_run.font.size = Pt(13)

    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    return buffer