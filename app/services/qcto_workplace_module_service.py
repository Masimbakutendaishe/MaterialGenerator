"""Builds the QCTO Workplace Module document — cover page, TOC, per-module intro/purpose,
sub-modules table, and per-unit content with Scope of Work Experience framing, nested Key
Work Activities (concept/process/example), example/tip callouts, and exercises."""
from io import BytesIO
from docx import Document
from docx.shared import Pt, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH
from app.services.ai_service import generate_qcto_workplace_module_content
from app.services.document_service import (
    _hex_to_rgb, _build_branded_cover, _add_signature_block, _add_branded_header_footer,
    _render_content_block, _add_bottom_border, DEFAULT_PRIMARY, DEFAULT_SECONDARY, DEFAULT_ACCENT,
)

def _add_wm_unit_scope_box(doc, unit, primary, primary_hex):
    """1-row bordered table: unit title + 'Scope of Work Experience' framing statement."""
    table = doc.add_table(rows=1, cols=1)
    table.style = "Table Grid"
    cell = table.rows[0].cells[0]
    title_p = cell.paragraphs[0]
    title_run = title_p.add_run(unit.get("unit_title", ""))
    title_run.bold = True
    title_run.font.color.rgb = primary

    scope_p = cell.add_paragraph()
    scope_run = scope_p.add_run(f"Scope of Work Experience: {unit.get('scope_statement', '')}")
    scope_run.italic = True
    doc.add_paragraph()


def _add_wm_reflection_box(doc, module, primary_hex, secondary_hex):
    """Module-level reflection box, pulling from the module's real work_experience_elements
    as source material for reflection prompts."""
    heading = doc.add_paragraph()
    h_run = heading.add_run("Reflect on Your Workplace Experience")
    h_run.bold = True
    _add_bottom_border(heading, primary_hex, size="8")

    doc.add_paragraph("Write your own notes to remember:")

    elements = module.get("work_experience_elements") or []
    element_texts = [e.get("text", "") if isinstance(e, dict) else (e or "") for e in elements]
    prompts = (element_texts[:5] + [""] * 5)[:5]

    table = doc.add_table(rows=5, cols=1)
    table.style = "Table Grid"
    for i, prompt in enumerate(prompts):
        cell = table.rows[i].cells[0]
        label = f"{i + 1}. " + (prompt if prompt else "_" * 80)
        cell.text = label

    doc.add_paragraph()


def _add_wm_back_matter(doc, primary, primary_hex):
    """Generic WM annexures — a workplace evidence log and a new-terms glossary."""
    heading = doc.add_paragraph()
    h_run = heading.add_run("Workplace Evidence Log")
    h_run.bold = True
    h_run.font.size = Pt(18)
    h_run.font.color.rgb = primary
    _add_bottom_border(heading, primary_hex)

    doc.add_paragraph("Use this log to record real workplace evidence as you complete each work experience activity.")
    table = doc.add_table(rows=1, cols=3)
    table.style = "Table Grid"
    hdr = table.rows[0].cells
    hdr[0].text, hdr[1].text, hdr[2].text = "Date", "Activity / Evidence", "Supervisor Sign-off"
    for c in hdr:
        c.paragraphs[0].runs[0].bold = True
    for _ in range(8):
        table.add_row()

    doc.add_page_break()

    glossary_heading = doc.add_paragraph()
    gh_run = glossary_heading.add_run("Words That Are New to Me")
    gh_run.bold = True
    gh_run.font.size = Pt(18)
    gh_run.font.color.rgb = primary
    _add_bottom_border(glossary_heading, primary_hex)

    g_table = doc.add_table(rows=1, cols=2)
    g_table.style = "Table Grid"
    g_hdr = g_table.rows[0].cells
    g_hdr[0].text, g_hdr[1].text = "Term", "My Definition"
    for c in g_hdr:
        c.paragraphs[0].runs[0].bold = True
    for _ in range(8):
        g_table.add_row()



def build_qcto_workplace_module_docx(title: str, syllabus_content: dict, organization_name: str = None,
                                      logo_bytes: bytes = None, brand_colors: dict = None,
                                      job_id: str = None) -> BytesIO:
    brand_colors = brand_colors or {}
    primary_hex = brand_colors.get("primary", DEFAULT_PRIMARY).lstrip("#") if brand_colors.get("primary") else DEFAULT_PRIMARY
    secondary_hex = brand_colors.get("secondary", DEFAULT_SECONDARY).lstrip("#") if brand_colors.get("secondary") else DEFAULT_SECONDARY
    accent_hex = brand_colors.get("accent", DEFAULT_ACCENT).lstrip("#") if brand_colors.get("accent") else DEFAULT_ACCENT
    primary = _hex_to_rgb(primary_hex, DEFAULT_PRIMARY)
    secondary = _hex_to_rgb(secondary_hex, DEFAULT_SECONDARY)
    qualification_title = syllabus_content.get("qualification_title", "") or title

    doc = Document()
    _build_branded_cover(doc, qualification_title, "WM Guide", organization_name, logo_bytes, primary, primary_hex, secondary)

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
            _add_wm_unit_scope_box(doc, unit, primary, primary_hex)

            unit_heading = doc.add_paragraph()
            uh_run = unit_heading.add_run(f"Unit {m_index}.{u_index}: {unit.get('unit_title', '')}")
            uh_run.bold = True
            uh_run.font.size = Pt(15)
            uh_run.font.color.rgb = secondary

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

        _add_wm_reflection_box(doc, module, primary_hex, secondary_hex)

        doc.add_page_break()

    _add_wm_back_matter(doc, primary, primary_hex)

    _add_signature_block(doc)
    _add_branded_header_footer(doc, logo_bytes=logo_bytes, qualification_name=title, organization_name=organization_name, primary_hex=primary_hex)

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
