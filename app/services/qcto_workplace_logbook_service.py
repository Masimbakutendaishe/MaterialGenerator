"""Builds the QCTO Workplace Logbook — a blank fillable template for learners to record
daily on-the-job activities. No AI content generation; this is a repeated static form,
one 'Daily Work Log Entry' block per module, matching the real Ishida reference format."""
from io import BytesIO
from docx import Document
from docx.shared import Pt, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH
from app.services.document_service import (
    _hex_to_rgb, _build_branded_cover, _add_page_numbers, _add_bottom_border,
    DEFAULT_PRIMARY, DEFAULT_SECONDARY,
)

# How many blank daily-entry pages to generate per module — enough for a real training period
ENTRIES_PER_MODULE = 10


def _add_daily_log_entry(doc, primary_hex):
    """Adds one blank 'Daily Work Log Entry' block matching the reference format exactly."""
    date_p = doc.add_paragraph()
    date_p.add_run("Date: " + "_" * 50)
    date_p.paragraph_format.space_before = Pt(10)

    desc_heading = doc.add_paragraph()
    desc_run = desc_heading.add_run("Work Activity Description")
    desc_run.bold = True
    desc_sub = desc_heading.add_run(" (Write what tasks you performed today)")
    desc_sub.italic = True
    desc_sub.font.size = Pt(9)

    for _ in range(4):
        line_p = doc.add_paragraph()
        line_p.paragraph_format.space_after = Pt(6)
        line_p.add_run("_" * 100)

    for label in ["Activity Code(s) Performed:", "Location / Section of Work:", "Machinery Worked On:"]:
        field_p = doc.add_paragraph()
        field_p.add_run(f"{label} " + "_" * 50)
        field_p.paragraph_format.space_after = Pt(8)

    learnt_heading = doc.add_paragraph()
    learnt_heading.add_run("What I Learnt Today:").bold = True
    for _ in range(2):
        line_p = doc.add_paragraph()
        line_p.paragraph_format.space_after = Pt(6)
        line_p.add_run("_" * 100)

    query_heading = doc.add_paragraph()
    query_heading.add_run("Queries or Questions Related to Today's Activity:").bold = True
    for _ in range(2):
        line_p = doc.add_paragraph()
        line_p.paragraph_format.space_after = Pt(6)
        line_p.add_run("_" * 100)

    sig_heading = doc.add_paragraph()
    sig_heading.add_run("Signatures").bold = True
    sig_heading.paragraph_format.space_before = Pt(10)
    for label in ["Learner's Signature:", "Industrial Supervisor's Signature:", "Facilitator's Signature:"]:
        sig_p = doc.add_paragraph()
        sig_p.add_run(f"{label}  " + "_" * 40)
        sig_p.paragraph_format.space_after = Pt(6)


def build_qcto_workplace_logbook_docx(title: str, syllabus_content: dict, organization_name: str = None,
                                       logo_bytes: bytes = None, brand_colors: dict = None,
                                       job_id: str = None) -> BytesIO:
    brand_colors = brand_colors or {}
    primary_hex = brand_colors.get("primary", DEFAULT_PRIMARY).lstrip("#") if brand_colors.get("primary") else DEFAULT_PRIMARY
    primary = _hex_to_rgb(primary_hex, DEFAULT_PRIMARY)

    doc = Document()
    _build_branded_cover(doc, title, "Workplace Logbook", organization_name, logo_bytes, primary, primary_hex, primary)

    # Learner details table (front page, filled once)
    details_heading = doc.add_paragraph()
    details_heading.add_run("Learner Details (Fill on the first page only)").bold = True

    table = doc.add_table(rows=6, cols=2)
    table.style = "Table Grid"
    fields = ["Full Name", "Employee / Learner ID", "Department", "Supervisor Name",
              "Facilitator Name", "Logbook Start Date"]
    for i, field in enumerate(fields):
        table.cell(i, 0).text = field
        table.cell(i, 0).paragraphs[0].runs[0].bold = True

    doc.add_page_break()

    # How to Use section
    how_heading = doc.add_paragraph()
    how_run = how_heading.add_run("How to Use This Logbook")
    how_run.bold = True
    how_run.font.size = Pt(16)
    how_run.font.color.rgb = primary
    _add_bottom_border(how_heading, primary_hex)

    how_text = doc.add_paragraph(
        "This logbook is designed to help you systematically record your daily work activities, "
        "learning experiences, and any challenges you encounter while operating machinery in the "
        "workplace. Keeping detailed and accurate records helps you track your progress, provides "
        "evidence of your hands-on experience for assessment purposes, and supports clear "
        "communication with your supervisors and facilitators."
    )
    how_text.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY

    instructions = [
        "Fill in your personal details in the Learner Details section on the first page.",
        "For each workday or shift, complete a new Daily Work Log Entry page.",
        "Record the date, tasks performed, relevant activity codes, and location/machinery worked on.",
        "Reflect on what you learnt and note any questions for your supervisor or facilitator.",
        "Obtain signatures from yourself, your supervisor, and your facilitator for each entry.",
    ]
    for item in instructions:
        doc.add_paragraph(item, style="List Number")

    doc.add_page_break()

    wm_modules = [m for m in syllabus_content.get("modules", []) if m.get("module_type") == "WM"]

    for m_index, module in enumerate(wm_modules, start=1):
        module_heading = doc.add_paragraph()
        mh_run = module_heading.add_run(f"Module {m_index} Logs: {module.get('title', '')}")
        mh_run.bold = True
        mh_run.font.size = Pt(16)
        mh_run.font.color.rgb = primary
        _add_bottom_border(module_heading, primary_hex)

        for entry_num in range(ENTRIES_PER_MODULE):
            _add_daily_log_entry(doc, primary_hex)
            if entry_num < ENTRIES_PER_MODULE - 1:
                doc.add_page_break()

        doc.add_page_break()

    _add_page_numbers(doc)

    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    return buffer


def build_qcto_workplace_logbook_docx_adapter(title, units, organization_name=None, seta=None,
                                               nqf_level=None, logo_bytes=None, brand_colors=None,
                                               job_id=None, **kwargs):
    """Adapter matching the standard DOCUMENT_BUILDERS call signature."""
    syllabus_content = {"modules": units} if isinstance(units, list) else (units or {"modules": []})
    return build_qcto_workplace_logbook_docx(
        title=title,
        syllabus_content=syllabus_content,
        organization_name=organization_name,
        logo_bytes=logo_bytes,
        brand_colors=brand_colors,
        job_id=job_id,
    )