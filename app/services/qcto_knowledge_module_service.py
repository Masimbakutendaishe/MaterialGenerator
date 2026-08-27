"""Builds the QCTO Knowledge Module document — cover page, TOC, per-module intro/purpose,
a sub-modules/units table, and detailed per-topic content with example/tip callouts,
matching the real structural pattern of accredited QCTO training material."""
from io import BytesIO
from docx import Document
from docx.shared import Pt, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH
from app.services.ai_service import generate_qcto_knowledge_module_content
from app.services.document_service import (
    _hex_to_rgb, _build_branded_cover, _add_signature_block, _add_page_numbers,
    _render_content_block, _add_bottom_border, DEFAULT_PRIMARY, DEFAULT_SECONDARY, DEFAULT_ACCENT,
)


def build_qcto_knowledge_module_docx(title: str, syllabus_content: dict, organization_name: str = None,
                                      logo_bytes: bytes = None, brand_colors: dict = None,
                                      job_id: str = None) -> BytesIO:
    brand_colors = brand_colors or {}
    primary_hex = brand_colors.get("primary", DEFAULT_PRIMARY).lstrip("#") if brand_colors.get("primary") else DEFAULT_PRIMARY
    secondary_hex = brand_colors.get("secondary", DEFAULT_SECONDARY).lstrip("#") if brand_colors.get("secondary") else DEFAULT_SECONDARY
    accent_hex = brand_colors.get("accent", DEFAULT_ACCENT).lstrip("#") if brand_colors.get("accent") else DEFAULT_ACCENT
    primary = _hex_to_rgb(primary_hex, DEFAULT_PRIMARY)
    secondary = _hex_to_rgb(secondary_hex, DEFAULT_SECONDARY)

    doc = Document()
    _build_branded_cover(doc, title, "Knowledge Modules", organization_name, logo_bytes, primary, primary_hex, secondary)

    # Learner/Facilitator/Date lines on their own page after the cover
    for label in ["Learner Name:", "Facilitator Name:", "Date of Submission:"]:
        p = doc.add_paragraph()
        p.add_run(f"{label} " + "_" * 40)
        p.paragraph_format.space_after = Pt(14)
    doc.add_page_break()

    km_modules = [m for m in syllabus_content.get("modules", []) if m.get("module_type") == "KM"]

    # Table of Contents (simple styled list — real page numbers aren't feasible without
    # Word's native TOC field mechanics, so this lists modules/topics for navigation reference)
    toc_heading = doc.add_paragraph()
    toc_run = toc_heading.add_run("Table of Contents")
    toc_run.bold = True
    toc_run.font.size = Pt(18)
    toc_run.font.color.rgb = primary
    _add_bottom_border(toc_heading, primary_hex)

    for m_index, module in enumerate(km_modules, start=1):
        mod_p = doc.add_paragraph()
        mod_p.add_run(f"Module {m_index}: {module.get('title', '')}").bold = True
        for topic in module.get("topics", []):
            topic_p = doc.add_paragraph()
            topic_p.paragraph_format.left_indent = Inches(0.3)
            topic_p.add_run(f"{topic.get('topic_code', '')} — {topic.get('title', '')}")

    doc.add_page_break()

    # Per-module content
    for m_index, module in enumerate(km_modules, start=1):
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

        content = generate_qcto_knowledge_module_content(module, job_id=job_id)

        intro_heading = doc.add_paragraph()
        intro_heading.add_run("Introduction").bold = True
        intro_p = doc.add_paragraph(content.get("module_intro", ""))
        intro_p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY

        purpose_heading = doc.add_paragraph()
        purpose_heading.add_run("Purpose").bold = True
        purpose_p = doc.add_paragraph(content.get("module_purpose", ""))
        purpose_p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY

        # Sub-modules and Units table
        subheading = doc.add_paragraph()
        subheading.add_run("Sub-modules and Units").bold = True

        table = doc.add_table(rows=1, cols=2)
        table.style = "Table Grid"
        hdr = table.rows[0].cells
        hdr[0].text = "Learning Unit Code"
        hdr[1].text = "Learning Unit Title"
        for cell in hdr:
            cell.paragraphs[0].runs[0].bold = True
            cell.paragraphs[0].runs[0].font.size = Pt(10)

        for topic in module.get("topics", []):
            row = table.add_row().cells
            row[0].text = topic.get("topic_code", "")
            row[1].text = topic.get("title", "")
            for cell in row:
                for p in cell.paragraphs:
                    for r in p.runs:
                        r.font.size = Pt(9)

        doc.add_paragraph()

        # Per-topic detailed content
        for topic_content in content.get("topics", []):
            topic_heading = doc.add_paragraph()
            th_run = topic_heading.add_run(f"{topic_content.get('topic_code', '')} — {topic_content.get('topic_title', '')}")
            th_run.bold = True
            th_run.font.size = Pt(15)
            th_run.font.color.rgb = secondary

            for block in topic_content.get("blocks", []):
                _render_content_block(doc, block, primary_hex, secondary, accent_hex=accent_hex)

        doc.add_page_break()

    _add_signature_block(doc)
    _add_page_numbers(doc)

    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    return buffer


def build_qcto_knowledge_module_docx_adapter(title, units, organization_name=None, seta=None,
                                              nqf_level=None, logo_bytes=None, brand_colors=None,
                                              job_id=None, **kwargs):
    """Adapter matching the standard DOCUMENT_BUILDERS call signature (title, units, ...)
    used by generate_package_document_task, translating it to this builder's actual
    signature (syllabus_content instead of units, no seta/nqf_level)."""
    syllabus_content = {"modules": units} if isinstance(units, list) else (units or {"modules": []})
    return build_qcto_knowledge_module_docx(
        title=title,
        syllabus_content=syllabus_content,
        organization_name=organization_name,
        logo_bytes=logo_bytes,
        brand_colors=brand_colors,
        job_id=job_id,
    )