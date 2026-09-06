"""Builds the QCTO Practical Module document — cover page, front matter, TOC, per-module
intro/purpose, a sub-modules table, and per-unit content with a boxed Scope of Practical
Skill divider, detailed content, example/tip callouts, exercises, a module-level reflection
box (PM's real assessment criteria live at module level, not per-unit), and back matter —
matching the real structural pattern."""
from io import BytesIO
from docx import Document
from docx.shared import Pt, Inches, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from app.services.ai_service import generate_qcto_practical_module_content, parallel_map
from app.services.document_service import (
    _hex_to_rgb, _build_branded_cover, _add_signature_block, _add_branded_header_footer,
    _render_content_block, _add_bottom_border, _element_text, _element_code,
    DEFAULT_PRIMARY, DEFAULT_SECONDARY, DEFAULT_ACCENT,
)


def _add_pm_front_matter(doc, primary, primary_hex, secondary):
    """Static front-matter pages for the PM learner guide: welcome + methodology, framed
    around the practical/hands-on nature of these modules."""

    def _section_heading(text, size=16):
        p = doc.add_paragraph()
        run = p.add_run(text)
        run.bold = True
        run.font.size = Pt(size)
        run.font.color.rgb = primary
        _add_bottom_border(p, primary_hex, size="8")
        return p

    _section_heading("Welcome to the Practical Modules")
    doc.add_paragraph(
        "This guide covers the practical, hands-on component of your qualification. Follow "
        "along as your facilitator demonstrates each skill, and use the exercises to practise "
        "and reflect on what you have learnt."
    )

    _section_heading("Programme Methodology")
    doc.add_paragraph(
        "Practical modules are delivered through facilitator demonstration, guided practice, "
        "and hands-on exercises. You are expected to actively participate in every scenario "
        "and exercise, not just observe."
    )

    doc.add_page_break()


def _add_unit_scope_box(doc, unit, primary, primary_hex):
    """Boxed divider preceding a unit's detailed content — replaces the old inline 'Scope
    of Practical Skill' paragraph with a proper visual section break, matching the KM
    outcome-box treatment. No percentage row: unlike KM topics, PM units are AI-grouped
    from a flat performance-assessment list and carry no stable per-unit weight."""
    table = doc.add_table(rows=1, cols=1)
    table.style = "Table Grid"
    cell = table.rows[0].cells[0]
    title_run = cell.paragraphs[0].add_run(unit.get("unit_title", ""))
    title_run.bold = True
    title_run.font.size = Pt(13)
    title_run.font.color.rgb = primary

    scope_p = cell.add_paragraph()
    scope_label = scope_p.add_run("Scope of Practical Skill: ")
    scope_label.bold = True
    scope_label.italic = True
    scope_label.font.size = Pt(10)
    scope_text = scope_p.add_run(unit.get("scope_statement", ""))
    scope_text.italic = True
    scope_text.font.size = Pt(10)

    doc.add_paragraph()


def _add_module_reflection_box(doc, module, primary_hex, secondary_hex):
    """'Write your own notes to remember' reflection box closing out a module — one per
    module (not per-unit), since PM's real assessment_criteria live at the module level,
    not per-unit like KM's topics."""
    prompts = module.get("assessment_criteria") or []

    table = doc.add_table(rows=1, cols=1)
    table.style = "Table Grid"
    cell = table.rows[0].cells[0]

    heading_run = cell.paragraphs[0].add_run("Write your own notes to remember:")
    heading_run.bold = True
    heading_run.font.size = Pt(11)
    heading_run.font.color.rgb = _hex_to_rgb(primary_hex, DEFAULT_PRIMARY)

    for i, prompt in enumerate(prompts[:5], start=1):
        p = cell.add_paragraph()
        p.add_run(f"{i}. {prompt}")
        p.paragraph_format.space_after = Pt(6)
    for i in range(len(prompts[:5]) + 1, 6):
        p = cell.add_paragraph()
        p.add_run(f"{i}. " + "_" * 60)
        p.paragraph_format.space_after = Pt(6)

    module_code = module.get("module_code", "")
    code_p = doc.add_paragraph()
    code_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    code_run = code_p.add_run(f"IAC-{module_code}: Practical competence for this module can be demonstrated")
    code_run.italic = True
    code_run.bold = True
    code_run.font.size = Pt(10)
    code_run.font.color.rgb = _hex_to_rgb(secondary_hex, DEFAULT_SECONDARY)
    doc.add_paragraph()


def _add_pm_back_matter(doc, primary, primary_hex):
    """Back-matter annexure for the PM learner guide: a practical-skills evidence log for
    facilitator sign-off, matching how PoE-style evidence is tracked in accredited material."""

    def _section_heading(text):
        p = doc.add_paragraph()
        run = p.add_run(text)
        run.bold = True
        run.font.size = Pt(16)
        run.font.color.rgb = primary
        _add_bottom_border(p, primary_hex, size="8")
        return p

    doc.add_page_break()
    _section_heading("Annexure: Practical Skills Evidence Log")
    table = doc.add_table(rows=1, cols=3)
    table.style = "Table Grid"
    for i, text in enumerate(["Skill Demonstrated", "Date", "Facilitator Sign-off"]):
        table.rows[0].cells[i].text = text
        table.rows[0].cells[i].paragraphs[0].runs[0].bold = True
    for _ in range(5):
        table.add_row()


def build_qcto_practical_module_docx(title: str, syllabus_content: dict, organization_name: str = None,
                                      logo_bytes: bytes = None, brand_colors: dict = None,
                                      accreditation_info: dict = None, job_id: str = None) -> BytesIO:
    accreditation_info = dict(accreditation_info or {})
    if syllabus_content.get("qualification_code"):
        accreditation_info.setdefault("qualification_code", syllabus_content.get("qualification_code"))
    brand_colors = brand_colors or {}
    primary_hex = brand_colors.get("primary", DEFAULT_PRIMARY).lstrip("#") if brand_colors.get("primary") else DEFAULT_PRIMARY
    secondary_hex = brand_colors.get("secondary", DEFAULT_SECONDARY).lstrip("#") if brand_colors.get("secondary") else DEFAULT_SECONDARY
    accent_hex = brand_colors.get("accent", DEFAULT_ACCENT).lstrip("#") if brand_colors.get("accent") else DEFAULT_ACCENT
    primary = _hex_to_rgb(primary_hex, DEFAULT_PRIMARY)
    secondary = _hex_to_rgb(secondary_hex, DEFAULT_SECONDARY)
    qualification_title = syllabus_content.get("qualification_title", "") or title

    doc = Document()
    _build_branded_cover(doc, qualification_title, "PM Learner Guide", organization_name, logo_bytes, primary, primary_hex, secondary)

    _add_pm_front_matter(doc, primary, primary_hex, secondary)

    details_table = doc.add_table(rows=5, cols=2)
    details_table.style = "Table Grid"
    for i, field in enumerate(["Learner Name", "Facilitator Name", "Assessor Name", "Moderator Name", "Date of Submission"]):
        details_table.cell(i, 0).text = field
        details_table.cell(i, 0).paragraphs[0].runs[0].bold = True
    doc.add_page_break()

    pm_modules = [m for m in syllabus_content.get("modules", []) if m.get("module_type") == "PM"]

    toc_heading = doc.add_paragraph()
    toc_run = toc_heading.add_run("Table of Contents")
    toc_run.bold = True
    toc_run.font.size = Pt(18)
    toc_run.font.color.rgb = primary
    _add_bottom_border(toc_heading, primary_hex)

    for m_index, module in enumerate(pm_modules, start=1):
        mod_p = doc.add_paragraph()
        mod_p.add_run(f"Module {m_index}: {module.get('title', '')}").bold = True

    doc.add_page_break()

    module_contents = [None] * len(pm_modules)
    modules_needing_fetch = []
    fetch_positions = []
    for m_idx, module in enumerate(pm_modules):
        cached = module.get("generated_pm_content")
        if cached:
            module_contents[m_idx] = cached
        else:
            modules_needing_fetch.append(module)
            fetch_positions.append(m_idx)

    if modules_needing_fetch:
        fetched = parallel_map(
            modules_needing_fetch,
            lambda m: generate_qcto_practical_module_content(m, job_id=job_id),
            max_workers=3,
        )
        for pos, result in zip(fetch_positions, fetched):
            module_contents[pos] = result

    for m_index, module in enumerate(pm_modules, start=1):
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

        content = module_contents[m_index - 1]
        if content is None:
            content = {
                "module_intro": f"Content generation failed for {module.get('title', '')} — please regenerate this document.",
                "module_purpose": "",
                "units": [],
            }

        intro_heading = doc.add_paragraph()
        intro_heading.add_run("Introduction").bold = True
        intro_p = doc.add_paragraph(content.get("module_intro", ""))
        intro_p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY

        purpose_heading = doc.add_paragraph()
        purpose_heading.add_run("Purpose").bold = True
        purpose_p = doc.add_paragraph(content.get("module_purpose", ""))
        purpose_p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY

        pa_items = module.get("performance_assessment") or []
        if pa_items:
            ref_p = doc.add_paragraph()
            ref_run = ref_p.add_run("Performance Assessment Elements Covered in This Module:")
            ref_run.bold = True
            ref_run.italic = True
            ref_run.font.size = Pt(10)
            ref_run.font.color.rgb = secondary
            for pa in pa_items:
                code = pa.get("code") if isinstance(pa, dict) else None
                text = pa.get("text", "") if isinstance(pa, dict) else (pa or "")
                label = f"{code}: {text}" if code else text
                item_p = doc.add_paragraph(label, style="List Bullet")
                for run in item_p.runs:
                    run.font.size = Pt(10)
                    run.italic = True
            doc.add_paragraph()

        for u_index, unit in enumerate(content.get("units", []), start=1):
            _add_unit_scope_box(doc, unit, primary, primary_hex)

            unit_heading = doc.add_paragraph()
            uh_run = unit_heading.add_run(f"Unit {m_index}.{u_index}: {unit.get('unit_title', '')}")
            uh_run.bold = True
            uh_run.font.size = Pt(15)
            uh_run.font.color.rgb = secondary

            for block in unit.get("blocks", []):
                _render_content_block(doc, block, primary_hex, secondary, accent_hex=accent_hex)

        _add_module_reflection_box(doc, module, primary_hex, secondary_hex)

        doc.add_page_break()

    _add_pm_back_matter(doc, primary, primary_hex)

    _add_signature_block(doc)
    _add_branded_header_footer(doc, logo_bytes=logo_bytes, qualification_name=qualification_title, organization_name=organization_name, primary_hex=primary_hex, accreditation_info=accreditation_info, document_label="PM Learner Guide")

    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    return buffer


def build_qcto_practical_module_docx_adapter(title, units, organization_name=None, seta=None,
                                              nqf_level=None, logo_bytes=None, brand_colors=None,
                                              accreditation_info=None, job_id=None, **kwargs):
    """Adapter matching the standard DOCUMENT_BUILDERS call signature."""
    syllabus_content = {"modules": units} if isinstance(units, list) else (units or {"modules": []})
    return build_qcto_practical_module_docx(
        title=title,
        syllabus_content=syllabus_content,
        organization_name=organization_name,
        logo_bytes=logo_bytes,
        brand_colors=brand_colors,
        accreditation_info=accreditation_info,
        job_id=job_id,
    )