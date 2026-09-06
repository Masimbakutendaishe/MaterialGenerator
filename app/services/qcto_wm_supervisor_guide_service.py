"""Builds the QCTO WM Guide for Industry Supervisors — a compact, plain-language handout
for the workplace mentor/supervisor, distinct in audience and tone from the learner-facing
WM Guide. Uses the same real WM module data (work_experience_elements, guidelines) but
reframes it around exposure, observation, and sign-off rather than learning content, and
explicitly walks the supervisor through the exact sections of the real WM Logbook they will
be asked to complete — Witness Testimony, Scope of Work Experience, daily log sign-off, and
the Judgement Report — rather than describing a generic, disconnected process."""
from io import BytesIO
from docx import Document
from docx.shared import Pt, Inches, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from app.services.document_service import (
    _hex_to_rgb, _build_branded_cover, _add_branded_header_footer, _add_bottom_border,
    DEFAULT_PRIMARY, DEFAULT_SECONDARY,
)


def _section_heading(doc, text, primary, primary_hex, size=16):
    p = doc.add_paragraph()
    run = p.add_run(text)
    run.bold = True
    run.font.size = Pt(size)
    run.font.color.rgb = primary
    _add_bottom_border(p, primary_hex, size="8")
    return p


def _add_sup_welcome(doc, qualification_title, primary, primary_hex):
    _section_heading(doc, "Welcome, Workplace Supervisor", primary, primary_hex, size=18)
    doc.add_paragraph(
        f"One of your team members is currently working towards the {qualification_title}. "
        "As part of this qualification, they need real, supervised experience in your "
        "workplace — this is not paperwork for its own sake; it's how they actually become "
        "competent at the job, not just knowledgeable about it."
    )
    doc.add_paragraph(
        "This guide is written for you, not for a classroom. It tells you plainly what the "
        "learner needs exposure to, how to guide them through it, and exactly what you'll be "
        "asked to sign off in their WM Logbook. You don't need any teaching background to do "
        "this well — you just need to give them real work, watch how they do it, and be "
        "honest about what you see."
    )
    doc.add_page_break()


def _add_sup_role(doc, primary, primary_hex):
    _section_heading(doc, "Your Role as a Workplace Supervisor", primary, primary_hex)
    doc.add_paragraph(
        "Your role has four parts, and they happen roughly in this order for each skill area "
        "the learner needs to cover:"
    )
    for i, (label, desc) in enumerate([
        ("Expose", "Give the learner real access to the work — meetings, tasks, documents, decisions — not just a description of it."),
        ("Guide", "Let them observe you or an experienced team member first, then attempt tasks themselves with you nearby to answer questions."),
        ("Observe", "Once they're attempting the work, watch closely enough to notice how they actually handle it — not just whether they finished."),
        ("Sign Off", "When you're satisfied they can do it competently and consistently, record that in their WM Logbook."),
    ], start=1):
        p = doc.add_paragraph()
        p.add_run(f"{i}. {label}: ").bold = True
        p.add_run(desc)

    doc.add_paragraph()
    doc.add_paragraph(
        "You are not expected to teach theory — that's covered in the learner's Learning "
        "Guides before they get to you. Your job is to provide the real workplace conditions "
        "the learner needs to prove they can apply what they've learned."
    )
    doc.add_page_break()


def _add_sup_workplace_details(doc, primary, primary_hex):
    """Fillable details about the specific supervisor and their particular workplace/
    industry — since supervisors for the same qualification could be at very different
    types of workplaces, this gives the training provider real context per learner."""
    _section_heading(doc, "About You and Your Workplace", primary, primary_hex)
    doc.add_paragraph("Please complete this before you begin — it helps the training provider understand the context the learner is being supervised in.")
    table = doc.add_table(rows=6, cols=2)
    table.style = "Table Grid"
    for i, field in enumerate(["Supervisor Name", "Position / Role", "Company / Organisation",
                                "Industry / Sector", "Department / Work Unit", "Contact Details"]):
        table.cell(i, 0).text = field
        table.cell(i, 0).paragraphs[0].runs[0].bold = True
    doc.add_page_break()


def _add_sup_module_section(doc, module, module_index, primary, primary_hex, secondary):
    """Per-module exposure/observation guidance, now with a genuine per-element sign-off
    table (comments + Competent/Not Yet Competent) rather than a plain bullet list, so the
    supervisor has somewhere to actually record their assessment of each skill area."""
    _section_heading(doc, f"Work Experience Area {module_index}: {module.get('title', '')}", primary, primary_hex)

    if module.get("guidelines"):
        doc.add_paragraph("What competence in this area looks like:").runs[0].bold = True
        doc.add_paragraph(module["guidelines"])
        doc.add_paragraph()

    elements = module.get("work_experience_elements") or []
    if elements:
        doc.add_paragraph(
            "Please expose the learner to opportunities to do each of the following, and "
            "record your assessment once you've observed them:"
        ).runs[0].bold = True

        table = doc.add_table(rows=1, cols=3)
        table.style = "Table Grid"
        hdr = table.rows[0].cells
        hdr[0].text, hdr[1].text, hdr[2].text = "Work Experience Activity", "Your Comments", "Assessment"
        for c in hdr:
            c.paragraphs[0].runs[0].bold = True

        for element in elements:
            text = element.get("text", "") if isinstance(element, dict) else (element or "")
            row = table.add_row().cells
            row[0].text = text
            row[1].text = ""
            row[2].text = "☐ Competent   ☐ Not Yet Competent"

    doc.add_paragraph()
    doc.add_paragraph("A practical way to structure this:").runs[0].bold = True
    for step in [
        "Let the learner observe you or an experienced colleague handling this, once or twice.",
        "Have the learner attempt it themselves while you're available to guide and correct.",
        "Once they're consistently getting it right, let them handle it with normal light supervision.",
        "Note in the WM Logbook's Scope of Work Experience table when you're satisfied they can do this reliably.",
    ]:
        doc.add_paragraph(step, style="List Number")
    doc.add_page_break()


def _add_sup_logbook_walkthrough(doc, primary, primary_hex, secondary):
    """Explicit walkthrough of the real WM Logbook sections the supervisor will complete."""
    _section_heading(doc, "Completing the WM Logbook", primary, primary_hex, size=18)
    doc.add_paragraph(
        "The learner will bring you a document called the WM Logbook. It's where all of "
        "this gets recorded. Here's exactly what you'll be asked to do in it:"
    )

    sections = [
        (
            "Witness Testimony",
            "This is where you write your own account, in your own words, of how the learner "
            "has performed in the workplace. Be specific and honest — vague praise doesn't "
            "help the learner or their assessor. A few sentences on what you've actually seen "
            "them do well, and where they still need to improve, is worth more than a general "
            "endorsement."
        ),
        (
            "Scope of Work Experience",
            "A table listing each real work activity the learner needed exposure to. When "
            "you're satisfied they've genuinely handled one competently, add the date and "
            "your signature next to it."
        ),
        (
            "Daily Work Log Entries",
            "The learner fills these in themselves after each day or shift, describing what "
            "they did and learned. You'll be asked to countersign as the 'Industrial "
            "Supervisor's Signature' — only sign if what they've written genuinely matches "
            "what you saw them do."
        ),
        (
            "Judgement Report",
            "Towards the end of the process, the assessor uses a Judgement Report to decide "
            "whether the learner is ready to be marked competent. Your Witness Testimony and "
            "signed-off Scope of Work Experience entries are the main evidence they'll draw on "
            "from the workplace side — so the more specific and honest your input, the better "
            "that decision will be."
        ),
    ]

    for name, desc in sections:
        heading = doc.add_paragraph()
        heading.add_run(name).bold = True
        heading.runs[0].font.color.rgb = secondary
        doc.add_paragraph(desc)
        doc.add_paragraph()
    doc.add_page_break()


def _add_sup_tips(doc, primary, primary_hex):
    _section_heading(doc, "Tips for Being an Effective Workplace Mentor", primary, primary_hex)
    for tip in [
        "Give them real tasks with real consequences, not simulations or busywork — that's what actually builds competence.",
        "Say what you actually think. Vague, kind feedback doesn't help anyone improve.",
        "Don't sign off early because it's convenient — a premature sign-off doesn't do the learner any favours later.",
        "If you're worried about their progress, raise it early with the training provider rather than waiting until the final assessment.",
        "Let them make small mistakes under supervision — that's a safer place to learn than making them alone later.",
        "Be consistent — judge the same standard the same way each time, so your feedback is fair and useful.",
    ]:
        doc.add_paragraph(tip, style="List Bullet")
    doc.add_page_break()


def _add_sup_contact(doc, organization_name, primary, primary_hex):
    _section_heading(doc, "Questions or Concerns?", primary, primary_hex)
    provider_phrase = f", {organization_name}," if organization_name else ""
    doc.add_paragraph(
        f"If you have any questions about this process, or concerns about a learner's "
        f"progress, please contact the training provider{provider_phrase} directly rather "
        f"than waiting for a scheduled check-in."
    )
    table = doc.add_table(rows=3, cols=2)
    table.style = "Table Grid"
    for i, field in enumerate(["Facilitator Name & Contact", "Assessor Name & Contact", "Training Provider Office Contact"]):
        table.cell(i, 0).text = field
        table.cell(i, 0).paragraphs[0].runs[0].bold = True


def build_qcto_wm_supervisor_guide_docx(title: str, syllabus_content: dict, organization_name: str = None,
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

    wm_modules = [m for m in syllabus_content.get("modules", []) if m.get("module_type") == "WM"]

    doc = Document()
    _build_branded_cover(doc, qualification_title, "WM Guide for Industry Supervisors", organization_name, logo_bytes, primary, primary_hex, secondary)

    _add_sup_welcome(doc, qualification_title, primary, primary_hex)
    _add_sup_workplace_details(doc, primary, primary_hex)
    _add_sup_role(doc, primary, primary_hex)

    for i, module in enumerate(wm_modules, start=1):
        _add_sup_module_section(doc, module, i, primary, primary_hex, secondary)

    _add_sup_logbook_walkthrough(doc, primary, primary_hex, secondary)
    _add_sup_tips(doc, primary, primary_hex)
    _add_sup_contact(doc, organization_name, primary, primary_hex)

    _add_branded_header_footer(doc, logo_bytes=logo_bytes, qualification_name=qualification_title, organization_name=organization_name, primary_hex=primary_hex, accreditation_info=accreditation_info, document_label="WM Guide for Industry Supervisors")

    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    return buffer


def build_qcto_wm_supervisor_guide_docx_adapter(title, units, organization_name=None, seta=None,
                                                  nqf_level=None, logo_bytes=None, brand_colors=None,
                                                  accreditation_info=None, job_id=None, **kwargs):
    """Adapter matching the standard DOCUMENT_BUILDERS call signature."""
    syllabus_content = {"modules": units} if isinstance(units, list) else (units or {"modules": []})
    return build_qcto_wm_supervisor_guide_docx(
        title=title,
        syllabus_content=syllabus_content,
        organization_name=organization_name,
        logo_bytes=logo_bytes,
        brand_colors=brand_colors,
        accreditation_info=accreditation_info,
        job_id=job_id,
    )
