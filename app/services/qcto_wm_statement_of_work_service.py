"""Builds the Statement of Work Experience — lists each Work Experience Module's
elements, and for each element, a 'Scope Work Experience' activity breakdown (with
date/signature columns for supervisor sign-off) plus a standard Supporting Evidence
checklist, matching the real QCTO reference pattern (Section 4D)."""
from io import BytesIO
from docx import Document
from docx.shared import Pt
from app.services.ai_service import generate_wm_scope_of_work_activities, parallel_map
from app.services.document_service import (
    _hex_to_rgb, _build_branded_cover, _add_branded_header_footer, _add_bottom_border,
    DEFAULT_PRIMARY, DEFAULT_SECONDARY, DEFAULT_ACCENT, _set_default_font, _add_learner_registration_details,
)

SUPPORTING_EVIDENCE_ITEMS = [
    "Reports and action plans.",
    "Manager's Observation and evaluation Report.",
    "Minutes of Meetings.",
    "Peer and customer feedback.",
    "Signed Off Logbook.",
]


def build_qcto_wm_statement_of_work_docx(title: str, syllabus_content: dict, organization_name: str = None,
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
    qualification_code = accreditation_info.get("qualification_code", "")

    wm_modules = [m for m in syllabus_content.get("modules", []) if m.get("module_type") == "WM"]

    doc = Document()
    _set_default_font(doc, brand_colors.get("font"))
    _build_branded_cover(doc, qualification_title, "Statement of Work Experience", organization_name, logo_bytes, primary, primary_hex, secondary, accent_hex=accent_hex)

    heading = doc.add_paragraph()
    h_run = heading.add_run("Section 4D: Statement of Work Experience")
    h_run.bold = True
    h_run.font.size = Pt(16)
    h_run.font.color.rgb = primary
    _add_bottom_border(heading, primary_hex)

    meta_table = doc.add_table(rows=2, cols=2)
    meta_table.style = "Table Grid"
    meta_table.cell(0, 0).text = "Curriculum Number"
    meta_table.cell(0, 0).paragraphs[0].runs[0].bold = True
    meta_table.cell(0, 1).text = qualification_code
    meta_table.cell(1, 0).text = "Curriculum Title"
    meta_table.cell(1, 0).paragraphs[0].runs[0].bold = True
    meta_table.cell(1, 1).text = qualification_title
    doc.add_paragraph()

    modules_heading = doc.add_paragraph()
    modules_heading.add_run("Work Experience Modules Included in This Statement").bold = True
    total_credits = 0
    for module in wm_modules:
        credits = module.get("credits", 0)
        try:
            total_credits += int(credits)
        except (TypeError, ValueError):
            pass
        p = doc.add_paragraph(style="List Bullet")
        p.add_run(f"{module.get('module_code', '')}: {module.get('title', '')}, NQF Level {module.get('nqf_level', '')}, Credits {credits}.")
    total_p = doc.add_paragraph()
    total_p.add_run(f"Total number of credits for Work Experience Modules: {total_credits}").bold = True
    doc.add_page_break()

    _add_learner_registration_details(doc, primary, primary_hex)

    employer_heading = doc.add_paragraph()
    employer_heading.add_run("Employer Details").bold = True
    employer_table = doc.add_table(rows=0, cols=2)
    employer_table.style = "Table Grid"
    for field in ["Company", "Physical Address", "Supervisor Name", "Contact Details", "Email"]:
        row = employer_table.add_row()
        row.cells[0].text = field
        row.cells[0].paragraphs[0].runs[0].bold = True
    doc.add_page_break()

    # Flatten every WE element across every module, so activity generation runs concurrently
    we_items = []  # (module, module_index, we_text, we_code)
    for m_index, module in enumerate(wm_modules, start=1):
        elements = module.get("work_experience_elements", [])
        for e_index, we_text in enumerate(elements, start=1):
            we_code = f"WE{m_index:02d}{e_index:02d}"
            we_items.append((module, we_text, we_code))

    activity_results = parallel_map(
        we_items,
        lambda item: generate_wm_scope_of_work_activities(item[1], item[0].get("title", ""), job_id=job_id),
        max_workers=3,
    )
    activities_by_code = {item[2]: (result or []) for item, result in zip(we_items, activity_results)}

    for m_index, module in enumerate(wm_modules, start=1):
        module_heading = doc.add_paragraph()
        mh_run = module_heading.add_run(f"{module.get('module_code', '')}: {module.get('title', '')}, NQF Level {module.get('nqf_level', '')}, Credits {module.get('credits', '')}.")
        mh_run.bold = True
        mh_run.font.size = Pt(14)
        mh_run.font.color.rgb = primary
        _add_bottom_border(module_heading, primary_hex, size="6")

        elements = module.get("work_experience_elements", [])
        list_heading = doc.add_paragraph()
        list_heading.add_run("List of Experiences included in the module.").italic = True
        for e_index, we_text in enumerate(elements, start=1):
            we_code = f"WE{m_index:02d}{e_index:02d}"
            doc.add_paragraph(f"{we_code} {we_text}", style="List Bullet")

        for e_index, we_text in enumerate(elements, start=1):
            we_code = f"WE{m_index:02d}{e_index:02d}"
            we_heading = doc.add_paragraph()
            we_heading.add_run(f"{we_code} {we_text}").bold = True
            we_heading.runs[0].font.color.rgb = secondary

            scope_label = doc.add_paragraph()
            scope_label.add_run("Scope Work Experience").bold = True
            scope_table = doc.add_table(rows=1, cols=3)
            scope_table.style = "Table Grid"
            for i, h in enumerate(["Activity", "Date", "Signature"]):
                scope_table.rows[0].cells[i].text = h
                scope_table.rows[0].cells[i].paragraphs[0].runs[0].bold = True
            activities = activities_by_code.get(we_code, [])
            for a_index, activity_text in enumerate(activities, start=1):
                wa_code = f"WA{e_index:02d}{a_index:02d}"
                row = scope_table.add_row()
                row.cells[0].text = f"{wa_code} {activity_text}"

            doc.add_paragraph()
            evidence_label = doc.add_paragraph()
            evidence_label.add_run("Supporting Evidence").bold = True
            evidence_table = doc.add_table(rows=1, cols=3)
            evidence_table.style = "Table Grid"
            for i, h in enumerate(["Evidence", "Date", "Signature"]):
                evidence_table.rows[0].cells[i].text = h
                evidence_table.rows[0].cells[i].paragraphs[0].runs[0].bold = True
            for se_index, se_text in enumerate(SUPPORTING_EVIDENCE_ITEMS, start=1):
                row = evidence_table.add_row()
                row.cells[0].text = f"SE{se_index:02d} {se_text}"
            doc.add_paragraph()

        doc.add_page_break()

    _add_branded_header_footer(
        doc, logo_bytes=logo_bytes, qualification_name=qualification_title,
        organization_name=organization_name, primary_hex=primary_hex,
        accreditation_info=accreditation_info, document_label="Statement of Work Experience",
    )

    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    return buffer


def build_qcto_wm_statement_of_work_docx_adapter(title, units, organization_name=None, seta=None,
                                                  nqf_level=None, logo_bytes=None, brand_colors=None,
                                                  accreditation_info=None, job_id=None, **kwargs):
    """Adapter matching the standard DOCUMENT_BUILDERS call signature."""
    syllabus_content = {"modules": units} if isinstance(units, list) else (units or {"modules": []})
    return build_qcto_wm_statement_of_work_docx(
        title=title, syllabus_content=syllabus_content, organization_name=organization_name,
        logo_bytes=logo_bytes, brand_colors=brand_colors, accreditation_info=accreditation_info,
        job_id=job_id,
    )