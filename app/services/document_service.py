"""Builds a .docx textbook from structured syllabus content."""
from io import BytesIO
from docx import Document
from docx.shared import Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH
from app.services.ai_service import write_chapter_content


def build_textbook_docx(title: str, units: list, organization_name: str = None,
                         seta: str = None, nqf_level: str = None) -> BytesIO:
    doc = Document()

    title_para = doc.add_paragraph()
    title_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title_run = title_para.add_run(title)
    title_run.bold = True
    title_run.font.size = Pt(28)

    if organization_name:
        sub_para = doc.add_paragraph()
        sub_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
        sub_run = sub_para.add_run(organization_name)
        sub_run.font.size = Pt(14)

    doc.add_page_break()

    doc.add_heading("Table of Contents", level=1)
    for i, unit in enumerate(units, start=1):
        doc.add_paragraph(f"{i}. {unit.get('name', f'Unit {i}')}")
    doc.add_page_break()

    for i, unit in enumerate(units, start=1):
        unit_name = unit.get("name", f"Unit {i}")
        outcomes = unit.get("outcomes", [])

        doc.add_heading(unit_name, level=1)

        doc.add_heading("Learning Outcomes", level=2)
        for outcome in outcomes:
            doc.add_paragraph(outcome, style="List Bullet")

        chapter = write_chapter_content(unit_name, outcomes, seta=seta, nqf_level=nqf_level)

        # Intro
        if chapter.get("intro"):
            doc.add_paragraph(chapter["intro"])

        # Sections — real heading style per section, not just a paragraph
        for section in chapter.get("sections", []):
            heading = section.get("heading", "")
            body = section.get("body", "")
            if heading:
                doc.add_heading(heading, level=3)
            for para in body.split("\n\n"):
                cleaned = para.strip()
                if cleaned:
                    doc.add_paragraph(cleaned)

        # Key Points — real bullet list, real bold heading (not markdown asterisks)
        key_points = chapter.get("key_points", [])
        if key_points:
            doc.add_heading("Key Points", level=2)
            for point in key_points:
                doc.add_paragraph(point, style="List Bullet")

        doc.add_page_break()

    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    return buffer