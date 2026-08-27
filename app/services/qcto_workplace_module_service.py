"""Builds the QCTO Workplace Module document — cover page, TOC, per-module intro/purpose,
sub-modules table, and per-unit content with Scope of Work Experience framing, nested Key
Work Activities (concept/process/example), example/tip callouts, and exercises."""
from io import BytesIO
from docx import Document
from docx.shared import Pt, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH
from app.services.ai_service import generate_qcto_workplace_module_content
from app.services.document_service import (
    _hex_to_rgb, _build_branded_cover, _add_signature_block, _add_page_numbers,
    _render_content_block, _add_bottom_border, DEFAULT_PRIMARY, DEFAULT_SECONDARY, DEFAULT_ACCENT,
)


def build_qcto_workplace_module_docx(title: str, syllabus_content: dict, organization_name: str = None,
                                      logo_bytes: bytes = None, brand_colors: dict = None,
                                      job_id: str = None) -> BytesIO:
    brand_colors = brand_colors or {}
    primary_hex = brand_colors.get("primary", DEFAULT_PRIMARY).lstrip("#") if brand_colors.get("primary") else DEFAULT_PRIMARY
    secondary_hex = brand_colors.get("secondary", DEFAULT_SECONDARY).lstrip("#") if brand_colors.get("secondary") else DEFAULT_SECONDARY
    accent_hex = brand_colors.get("accent", DEFAULT_ACCENT).lstrip("#") if brand_colors.get("accent") else DEFAULT_ACCENT
    primary = _hex_to_rgb(primary_hex, DEFAULT_PRIMARY)
    secondary = _hex_to_rgb(secondary_hex, DEFAULT_SECONDARY)

    doc = Document()
    _build_branded_cover(doc, title, "Workplace Modules", organization_name, logo_bytes, primary, primary_hex, secondary)

    for label in ["Learner Name:", "Facilitator Name:", "Date of Submission:"]:
        p = doc.add_paragraph()
        p.add_run(f"{label} " + "_" * 40)
        p.paragraph_format.space_after = Pt(14)
    doc.add_page_break()

    wm_modules = [m for m in syllabus_content.get("modules", []) if m.get("module_type") == "WM"]

    toc_heading = doc.add_paragraph()
    toc_run = toc_heading.add_run("Table of Contents")
    toc_run.bold = True
    toc_run.font.size = Pt(18)
    toc_run.font.color.rgb = primary
    _add_bottom_border(toc_heading, primary_hex)

    for m_index, module in enumerate(wm_modules, start=1):
        mod_p = doc.add_paragraph()
        mod_p.add_run(f"Module {m_index}: {module.get('title', '')}").bold = True

    doc.add_page_break()

    for m_index, module in enumerate(wm_modules, start=1):
        module_heading = doc.add_paragraph()
        mh_run = module_heading.add_run(f"Module {m_index}: {module.get('title', '')}")
        mh_run.bold = True
        mh_run.font.size = Pt(20)
        mh_run.font.color.rgb = primary
        _add_bottom_border(module_heading, primary_hex)

        meta_p = doc.add_paragraph()
        meta_run = meta_p.add_run(f"{module.get('module_code', '')}  |  NQF Level {module.get('nqf_level', '')}  |  {module.get('credits', '')} Credits")
        meta_run.italic = True
        meta_run.font.size = Pt(10)

        content = generate_qcto_workplace_module_content(module, job_id=job_id)

        intro_heading = doc.add_paragraph()
        intro_heading.add_run("Introduction").bold = True
        intro_p = doc.add_paragraph(content.get("module_intro", ""))
        intro_p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY

        purpose_heading = doc.add_paragraph()
        purpose_heading.add_run("Purpose").bold = True
        purpose_p = doc.add_paragraph(content.get("module_purpose", ""))
        purpose_p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY

        for u_index, unit in enumerate(content.get("units", []), start=1):
            unit_heading = doc.add_paragraph()
            uh_run = unit_heading.add_run(f"Unit {m_index}.{u_index}: {unit.get('unit_title', '')}")
            uh_run.bold = True
            uh_run.font.size = Pt(15)
            uh_run.font.color.rgb = secondary

            scope_p = doc.add_paragraph()
            scope_label = scope_p.add_run("Scope of Work Experience\n")
            scope_label.bold = True
            scope_label.italic = True
            scope_label.font.size = Pt(10)
            scope_text = scope_p.add_run(unit.get("scope_statement", ""))
            scope_text.italic = True
            scope_text.font.size = Pt(10)

            for activity in unit.get("activities", []):
                act_heading = doc.add_paragraph()
                act_run = act_heading.add_run(f"{activity.get('activity_code', '')}: {activity.get('activity_title', '')}")
                act_run.bold = True
                act_run.font.size = Pt(12)
                act_run.font.color.rgb = primary

                if activity.get("concept_explanation"):
                    concept_label = doc.add_paragraph()
                    concept_label.add_run("Concept Explanation").bold = True
                    concept_label.runs[0].font.size = Pt(10)
                    for point in activity["concept_explanation"]:
                        doc.add_paragraph(point, style="List Bullet")

                if activity.get("process_steps"):
                    process_label = doc.add_paragraph()
                    process_label.add_run("Step-by-Step Process").bold = True
                    process_label.runs[0].font.size = Pt(10)
                    for step in activity["process_steps"]:
                        doc.add_paragraph(step, style="List Number")

                if activity.get("practical_example"):
                    ex_p = doc.add_paragraph()
                    ex_label = ex_p.add_run("Practical Example: ")
                    ex_label.bold = True
                    ex_label.italic = True
                    ex_label.font.size = Pt(10)
                    ex_text = ex_p.add_run(activity["practical_example"])
                    ex_text.italic = True
                    ex_text.font.size = Pt(10)

                doc.add_paragraph()

            if unit.get("example_tip"):
                _render_content_block(doc, {"type": "example_tip", **unit["example_tip"]}, primary_hex, secondary, accent_hex=accent_hex)
            if unit.get("exercise"):
                _render_content_block(doc, {"type": "exercise", **unit["exercise"]}, primary_hex, secondary, accent_hex=accent_hex)

        doc.add_page_break()

    _add_signature_block(doc)
    _add_page_numbers(doc)

    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    return buffer


def build_qcto_workplace_module_docx_adapter(title, units, organization_name=None, seta=None,
                                              nqf_level=None, logo_bytes=None, brand_colors=None,
                                              job_id=None, **kwargs):
    """Adapter matching the standard DOCUMENT_BUILDERS call signature."""
    syllabus_content = {"modules": units} if isinstance(units, list) else (units or {"modules": []})
    return build_qcto_workplace_module_docx(
        title=title,
        syllabus_content=syllabus_content,
        organization_name=organization_name,
        logo_bytes=logo_bytes,
        brand_colors=brand_colors,
        job_id=job_id,
    )