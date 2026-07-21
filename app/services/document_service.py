# Builds .docx from structured content
"""Builds a .docx textbook from structured syllabus content."""
from io import BytesIO
from docx import Document
from docx.shared import Pt, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH


def build_textbook_docx(title: str, units: list, organization_name: str = None) -> BytesIO:
    """Takes syllabus units (list of {"name": ..., "outcomes": [...]}) and produces
    a formatted .docx in memory. Returns a BytesIO ready to save or upload."""
    doc = Document()

    # Title page
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

    # Table of contents (simple text list — real TOC field can be added later)
    doc.add_heading("Table of Contents", level=1)
    for i, unit in enumerate(units, start=1):
        doc.add_paragraph(f"{i}. {unit.get('name', f'Unit {i}')}")
    doc.add_page_break()

    # Chapters
    for i, unit in enumerate(units, start=1):
        doc.add_heading(unit.get("name", f"Unit {i}"), level=1)

        doc.add_heading("Learning Outcomes", level=2)
        for outcome in unit.get("outcomes", []):
            doc.add_paragraph(outcome, style="List Bullet")

        doc.add_heading("Content", level=2)
        doc.add_paragraph(
            "[Content for this unit will be expanded here — this is a structural draft "
            "generated from the syllabus. Full explanatory text, examples, and exercises "
            "are added in the next generation pass.]"
        )

        doc.add_page_break()

    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    return buffer