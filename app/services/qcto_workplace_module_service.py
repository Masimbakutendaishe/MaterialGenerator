"""Builds the QCTO Workplace Module document — cover page, front matter, TOC, per-module
intro/purpose, sub-modules table, and per-unit content with a boxed Scope of Work Experience
divider, nested Key Work Activities (concept/process/example), example/tip callouts and
exercises, a blank reflection box per module (WM's extraction carries no assessment_criteria
field, so unlike KM/PM there's no real source data to populate reflection prompts with), and
back matter."""
from io import BytesIO
from docx import Document
from docx.shared import Pt, Inches, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from app.services.ai_service import generate_qcto_workplace_module_content, parallel_map
from app.services.document_service import (
    _hex_to_rgb, _build_branded_cover, _add_signature_block, _add_branded_header_footer,
    _render_content_block, _add_bottom_border, DEFAULT_PRIMARY, DEFAULT_SECONDARY, DEFAULT_ACCENT,
)


def _add_wm_front_matter(doc, primary, primary_hex, secondary):
    """Static front-matter pages for the WM guide: welcome + methodology, framed around
    real workplace experience completed under supervision."""

    def _section_heading(text, size=16):
        p = doc.add_paragraph()
        run = p.add_run(text)
        run.bold = True
        run.font.size = Pt(size)
        run.font.color.rgb = primary
        _add_bottom_border(p, primary_hex, size="8")
        return p

    _section_heading("Welcome to the Workplace Modules")
    doc.add_paragraph(
        "This guide covers the workplace experience component of your qualification — real "
        "tasks, completed under supervision, in a genuine work environment. Use your Workplace "
        "Logbook alongside this guide to record your progress."
    )

    _section_heading("Programme Methodology")
    doc.add_paragraph(
        "Workplace modules are completed on the job, under the guidance of a workplace "
        "supervisor. You are responsible for seeking out opportunities to complete each Key "
        "Work Activity and for keeping accurate records of what you have done."
    )
    doc.add_page_break()


def _add_wm_unit_scope_box(doc, unit, primary, primary_hex):
    """Boxed divider preceding a unit's content — replaces the old inline 'Scope of Work
    Experience' paragraph with a proper visual section break, matching the KM/PM treatment.
    No percentage row: WM units carry no per-unit weight data, same as PM."""
    table = doc.add_table(rows=1, cols=1)
    table.style = "Table Grid"
    cell = table.rows[0].cells[0]
    title_run = cell.paragraphs[0].add_run(unit.get("unit_title", ""))
    title_run.bold = True
    title_run.font.size = Pt(13)
    title_run.font.color.rgb = primary

    scope_p = cell.add_paragraph()
    scope_label = scope_p.add_run("Scope of Work Experience: ")
    scope_label.bold = True
    scope_label.italic = True
    scope_label.font.size = Pt(10)
    scope_text = scope_p.add_run(unit.get("scope_statement", ""))
    scope_text.italic = True
    scope_text.font.size = Pt(10)

    doc.add_paragraph()


def _add_wm_reflection_box(doc, module, primary_hex, secondary_hex):
    """Blank reflection box only — WM's extraction has no assessment_criteria field, so
    unlike KM/PM there's no real source data to populate reflection prompts with; fabricating
    them would violate the no-hallucination principle this whole build follows."""
    table = doc.add_table(rows=1, cols=1)
    table.style = "Table Grid"
    cell = table.rows[0].cells[0]

    heading_run = cell.paragraphs[0].add_run("Write your own notes to remember:")
    heading_run.bold = True
    heading_run.font.size = Pt(11)
    heading_run.font.color.rgb = _hex_to_rgb(primary_hex, DEFAULT_PRIMARY)

    for i in range(1, 6):
        p = cell.add_paragraph()
        p.add_run(f"{i}. " + "_" * 60)
        p.paragraph_format.space_after = Pt(6)

    doc.add_paragraph()


def _add_wm_back_matter(doc, primary, primary_hex):
    """Back-matter annexure for the WM guide: a workplace experience sign-off log for
    supervisor sign-off, matching the evidence-tracking nature of workplace modules."""

    def _section_heading(text):
        p = doc.add_paragraph()
        run = p.add_run(text)
        run.bold = True
        run.font.size = Pt(16)
        run.font.color.rgb = primary
        _add_bottom_border(p, primary_hex, size="8")
        return p

    doc.add_page_break()
    _section_heading("Annexure: Workplace Experience Sign-Off Log")
    table = doc.add_table(rows=1, cols=4)
    table.style = "Table Grid"
    for i, text in enumerate(["Key Work Activity", "Date Completed", "Evidence", "Supervisor Sign-off"]):
        table.rows[0].cells[i].text = text
        table.rows[0].cells[i].paragraphs[0].runs[0].bold = True
    for _ in range(6):
        table.add_row()


def build_qcto_workplace_module_docx(title: str, syllabus_content: dict, organization_name: str = None,
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
    _build_branded_cover(doc, qualification_title, "WM Guide", organization_name, logo_bytes, primary, primary_hex, secondary)

    _add_wm_front_matter(doc, primary, primary_hex, secondary)

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

    module_contents = [None] * len(wm_modules)
    modules_needing_fetch = []
    fetch_positions = []
    for m_idx, module in enumerate(wm_modules):
        cached = module.get("generated_wm_content")
        if cached:
            module_contents[m_idx] = cached
        else:
            modules_needing_fetch.append(module)
            fetch_positions.append(m_idx)

    if modules_needing_fetch:
        fetched = parallel_map(
            modules_needing_fetch,
            lambda m: generate_qcto_workplace_module_content(m, job_id=job_id),
            max_workers=3,
        )
        for pos, result in zip(fetch_positions, fetched):
            module_contents[pos] = result

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
    _add_branded_header_footer(doc, logo_bytes=logo_bytes, qualification_name=qualification_title, organization_name=organization_name, primary_hex=primary_hex, accreditation_info=accreditation_info, document_label="WM Guide")

    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    return buffer


def build_qcto_workplace_module_docx_adapter(title, units, organization_name=None, seta=None,
                                              nqf_level=None, logo_bytes=None, brand_colors=None,
                                              accreditation_info=None, job_id=None, **kwargs):
    """Adapter matching the standard DOCUMENT_BUILDERS call signature."""
    syllabus_content = {"modules": units} if isinstance(units, list) else (units or {"modules": []})
    return build_qcto_workplace_module_docx(
        title=title,
        syllabus_content=syllabus_content,
        organization_name=organization_name,
        logo_bytes=logo_bytes,
        brand_colors=brand_colors,
        accreditation_info=accreditation_info,
        job_id=job_id,
    )