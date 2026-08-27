"""Builds the QCTO Learning Matrix — a page-reference table showing where each real KM
topic, PM unit, and WM unit appears in its respective Learner Guide document. Since
python-docx has no way to know actual rendered page numbers (that's resolved by Word's
layout engine, not something computable ahead of time), this uses a word-count-based
calculation anchored to real, known points this system fully controls (cover page count,
front matter page count, module boundaries) — producing genuine page ranges grounded in
real content length, calibrated as accurately as possible against each document's actual
structure. Each row explicitly names which Learner Guide document it refers to (KM Learner
Guide, PM Learner Guide, or WM Guide), so there is no ambiguity about which file a page
range belongs to. This independently re-runs the same content-generation functions the
Learner Guides use, so exact wording (and therefore exact page count) can drift slightly
between two separate generations of the same curriculum, since AI output isn't perfectly
deterministic."""
from io import BytesIO
from docx import Document
from docx.shared import Pt, Inches, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from app.services.ai_service import (
    generate_qcto_knowledge_module_content,
    generate_qcto_practical_module_content,
    generate_qcto_workplace_module_content,
)
from app.services.document_service import (
    _hex_to_rgb, _build_branded_cover, _add_branded_header_footer, _add_bottom_border,
    DEFAULT_PRIMARY, DEFAULT_SECONDARY,
)

# Calibrated for this document's formatting (headings, tables, spacing between
# paragraphs) — not an exact science, but a reasonable, stated assumption.
WORDS_PER_PAGE = 450
COVER_PAGES = 1
KM_PM_FRONT_MATTER_PAGES = 4  # KM/PM front matter each carry ~3 real page breaks -> ~4 pages of content
WM_FRONT_MATTER_PAGES = 2  # WM Guide: just a learner-details page + TOC page, no elaborate front matter


def _count_words(value):
    """Sums words across a string, or a list/dict of strings/dicts with text-bearing
    fields — used to calculate how much page space a topic/unit's real generated content
    occupies."""
    if not value:
        return 0
    if isinstance(value, str):
        return len(value.split())
    if isinstance(value, list):
        return sum(_count_words(item) for item in value)
    if isinstance(value, dict):
        return sum(_count_words(v) for v in value.values())
    return 0


def _section_heading(doc, text, primary, primary_hex, size=18):
    p = doc.add_paragraph()
    run = p.add_run(text)
    run.bold = True
    run.font.size = Pt(size)
    run.font.color.rgb = primary
    _add_bottom_border(p, primary_hex, size="8")
    return p


def _add_matrix_intro(doc, primary, primary_hex):
    _section_heading(doc, "Learning Matrix", primary, primary_hex)
    doc.add_paragraph(
        "This matrix lists every Knowledge Module topic, Practical Module unit, and "
        "Workplace Module unit in this qualification, with the page range where it appears "
        "in its corresponding Learner Guide document."
    )
    note = doc.add_paragraph()
    note_run = note.add_run(
        "Page ranges are calculated from the real length of each item's generated content, "
        "anchored to known structural points in each document (cover page, front matter, "
        "module boundaries) — calibrated as accurately as possible against each document's "
        "actual structure. Because AI-generated wording can vary slightly between separate "
        "generations of the same curriculum, verify against the specific Learner Guide file "
        "you are using if exact precision matters."
    )
    note_run.italic = True
    note_run.font.size = Pt(9)
    doc.add_page_break()


def _estimate_km_ranges(km_modules, job_id=None):
    ranges = {}
    current_page = COVER_PAGES + KM_PM_FRONT_MATTER_PAGES + 1

    for module in km_modules:
        try:
            content = generate_qcto_knowledge_module_content(module, job_id=job_id)
        except Exception:
            content = {"topics": []}

        current_page += 1  # module intro/purpose/units-table overhead
        content_topics_by_code = {t.get("topic_code"): t for t in content.get("topics", [])}

        for topic in module.get("topics", []):
            topic_code = topic.get("topic_code", "")
            topic_content = content_topics_by_code.get(topic_code, {})
            words = _count_words(topic_content.get("blocks", []))
            pages_needed = max(1, round(words / WORDS_PER_PAGE + 0.5))
            start_page = current_page
            end_page = current_page + pages_needed - 1
            ranges[topic_code] = (module.get("module_code", ""), topic.get("title", ""), start_page, end_page)
            current_page = end_page + 1

        current_page += 1  # module boundary page break

    return ranges, current_page


def _estimate_pm_ranges(pm_modules, job_id=None):
    ranges = {}
    current_page = COVER_PAGES + KM_PM_FRONT_MATTER_PAGES + 1

    for module in pm_modules:
        try:
            content = generate_qcto_practical_module_content(module, job_id=job_id)
        except Exception:
            content = {"units": []}

        current_page += 1  # module intro/purpose overhead

        for unit in content.get("units", []):
            unit_title = unit.get("unit_title", "")
            words = _count_words(unit.get("blocks", []))
            pages_needed = max(1, round(words / WORDS_PER_PAGE + 0.5))
            start = current_page
            end = current_page + pages_needed - 1
            unit_key = f"{module.get('module_code', '')}::{unit_title}"
            ranges[unit_key] = (module.get("module_code", ""), unit_title, start, end)
            current_page = end + 1

        current_page += 1  # module boundary page break

    return ranges


def _estimate_wm_ranges(wm_modules, job_id=None):
    ranges = {}
    current_page = COVER_PAGES + WM_FRONT_MATTER_PAGES + 1

    for module in wm_modules:
        try:
            content = generate_qcto_workplace_module_content(module, job_id=job_id)
        except Exception:
            content = {"units": []}

        current_page += 1  # module intro/purpose overhead

        for unit in content.get("units", []):
            unit_title = unit.get("unit_title", "")
            words = (
                _count_words(unit.get("activities", []))
                + _count_words(unit.get("example_tip"))
                + _count_words(unit.get("exercise"))
            )
            pages_needed = max(1, round(words / WORDS_PER_PAGE + 0.5))
            start = current_page
            end = current_page + pages_needed - 1
            unit_key = f"{module.get('module_code', '')}::{unit_title}"
            ranges[unit_key] = (module.get("module_code", ""), unit_title, start, end)
            current_page = end + 1

        current_page += 1  # module boundary page break

    return ranges


def _add_matrix_table(doc, title, document_name, ranges, primary, primary_hex, label_col="Topic/Unit Code"):
    _section_heading(doc, title, primary, primary_hex, size=16)
    table = doc.add_table(rows=1, cols=5)
    table.style = "Table Grid"
    hdr = table.rows[0].cells
    hdr[0].text, hdr[1].text, hdr[2].text, hdr[3].text, hdr[4].text = "Module", label_col, "Title", "Learner Guide Document", "Page Range"
    for c in hdr:
        c.paragraphs[0].runs[0].bold = True
    for key, (module_code, title_text, start, end) in ranges.items():
        row = table.add_row().cells
        row[0].text = module_code
        row[1].text = key if "::" not in key else key.split("::", 1)[1]
        row[2].text = title_text
        row[3].text = document_name
        row[4].text = f"{start}-{end}" if start != end else str(start)
    doc.add_page_break()


def build_qcto_learning_matrix_docx(title: str, syllabus_content: dict, organization_name: str = None,
                                     logo_bytes: bytes = None, brand_colors: dict = None,
                                     job_id: str = None) -> BytesIO:
    brand_colors = brand_colors or {}
    primary_hex = brand_colors.get("primary", DEFAULT_PRIMARY).lstrip("#") if brand_colors.get("primary") else DEFAULT_PRIMARY
    secondary_hex = brand_colors.get("secondary", DEFAULT_SECONDARY).lstrip("#") if brand_colors.get("secondary") else DEFAULT_SECONDARY
    primary = _hex_to_rgb(primary_hex, DEFAULT_PRIMARY)
    secondary = _hex_to_rgb(secondary_hex, DEFAULT_SECONDARY)
    qualification_title = syllabus_content.get("qualification_title", "") or title

    all_modules = syllabus_content.get("modules", [])
    km_modules = [m for m in all_modules if m.get("module_type") == "KM"]
    pm_modules = [m for m in all_modules if m.get("module_type") == "PM"]
    wm_modules = [m for m in all_modules if m.get("module_type") == "WM"]

    km_ranges, _ = _estimate_km_ranges(km_modules, job_id=job_id)
    pm_ranges = _estimate_pm_ranges(pm_modules, job_id=job_id)
    wm_ranges = _estimate_wm_ranges(wm_modules, job_id=job_id)

    # Fix topic_code key display for KM table (it's not a "::"-joined key like PM/WM)
    km_ranges_fixed = {code: (mc, t, s, e) for code, (mc, t, s, e) in km_ranges.items()}

    doc = Document()
    _build_branded_cover(doc, qualification_title, "Learning Matrix", organization_name, logo_bytes, primary, primary_hex, secondary)

    _add_matrix_intro(doc, primary, primary_hex)

    _section_heading(doc, "Knowledge Module Topics", primary, primary_hex, size=16)
    table = doc.add_table(rows=1, cols=5)
    table.style = "Table Grid"
    hdr = table.rows[0].cells
    hdr[0].text, hdr[1].text, hdr[2].text, hdr[3].text, hdr[4].text = "Module", "Topic Code", "Title", "Learner Guide Document", "Page Range"
    for c in hdr:
        c.paragraphs[0].runs[0].bold = True
    for topic_code, (module_code, title_text, start, end) in km_ranges_fixed.items():
        row = table.add_row().cells
        row[0].text = module_code
        row[1].text = topic_code
        row[2].text = title_text
        row[3].text = "KM Learner Guide"
        row[4].text = f"{start}-{end}" if start != end else str(start)
    doc.add_page_break()

    _add_matrix_table(doc, "Practical Module Units", "PM Learner Guide", pm_ranges, primary, primary_hex, label_col="Unit")
    _add_matrix_table(doc, "Workplace Module Units", "WM Guide", wm_ranges, primary, primary_hex, label_col="Unit")

    _add_branded_header_footer(doc, logo_bytes=logo_bytes, qualification_name=qualification_title, organization_name=organization_name, primary_hex=primary_hex)

    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    return buffer


def build_qcto_learning_matrix_docx_adapter(title, units, organization_name=None, seta=None,
                                              nqf_level=None, logo_bytes=None, brand_colors=None,
                                              job_id=None, **kwargs):
    """Adapter matching the standard DOCUMENT_BUILDERS call signature."""
    syllabus_content = {"modules": units} if isinstance(units, list) else (units or {"modules": []})
    return build_qcto_learning_matrix_docx(
        title=title,
        syllabus_content=syllabus_content,
        organization_name=organization_name,
        logo_bytes=logo_bytes,
        brand_colors=brand_colors,
        job_id=job_id,
    )
