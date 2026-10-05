"""Builds a .docx textbook from structured syllabus content, styled with organization branding."""
from io import BytesIO
from docx import Document
from docx.shared import Pt, Inches, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
from app.services.ai_service import write_chapter_content
import io
import os

DEFAULT_PRIMARY = "1A5276"
DEFAULT_SECONDARY = "2874A6"
DEFAULT_ACCENT = "F39C12"

def _element_text(el) -> str:
    """Returns the display text for a topic/module element, handling both shapes safely:
    the current {"code": ..., "text": ...} dict shape, and the older plain-string shape
    still present in syllabi extracted before that change — so existing DB records don't
    break when rendered or consumed by document builders."""
    if isinstance(el, dict):
        return el.get("text", "") or ""
    return el or ""


def _element_code(el):
    """Returns the element's code if present (dict shape only), else None."""
    if isinstance(el, dict):
        return el.get("code")
    return None



def _hex_to_rgb(hex_str: str, fallback: str) -> RGBColor:
    try:
        return RGBColor.from_string((hex_str or fallback).lstrip("#").upper())
    except (ValueError, TypeError):
        return RGBColor.from_string(fallback)


def _add_bottom_border(paragraph, color_hex: str, size: str = "18"):
    p_pr = paragraph._p.get_or_add_pPr()
    p_borders = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), size)
    bottom.set(qn("w:space"), "4")
    bottom.set(qn("w:color"), color_hex.lstrip("#").upper())
    p_borders.append(bottom)
    p_pr.append(p_borders)


def _add_ruled_line(doc, color_hex: str, size: str = "6"):
    """Draws one full-width ruled line for handwritten answer space, using a real paragraph
    border rather than underscore characters. A border always spans exactly the text width
    regardless of font — underscore glyphs are font/size-dependent, and a fixed character
    count tuned to fit one font can overflow with another, wrapping the excess onto a short
    stray line."""
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(6)
    _add_bottom_border(p, color_hex, size=size)
    return p

def _add_full_border(paragraph, color_hex: str):
    """Adds a border on all four sides of a paragraph — used for scenario call-out boxes."""
    p_pr = paragraph._p.get_or_add_pPr()
    p_borders = OxmlElement("w:pBdr")
    for edge in ("top", "left", "bottom", "right"):
        border = OxmlElement(f"w:{edge}")
        border.set(qn("w:val"), "single")
        border.set(qn("w:sz"), "8")
        border.set(qn("w:space"), "8")
        border.set(qn("w:color"), color_hex.lstrip("#").upper())
        p_borders.append(border)
    p_pr.append(p_borders)

def _render_content_block(doc, block, primary_hex, secondary, accent_hex=None):
    if isinstance(block, str):
        # Defensive: some AI responses occasionally emit a raw string instead of a
        # proper {"type": "paragraph", "text": ...} block — treat it as plain paragraph text.
        block = {"type": "paragraph", "text": block}
    block_type = block.get("type", "paragraph")

    if block_type == "scenario":
        label_p = doc.add_paragraph()
        label_p.paragraph_format.space_before = Pt(10)
        _shade_paragraph(label_p, "F4F6F8")  # light steel background
        _add_full_border(label_p, primary_hex)
        label_run = label_p.add_run("WORKPLACE SCENARIO")
        label_run.bold = True
        label_run.font.size = Pt(10)
        label_run.font.color.rgb = secondary

        text_p = doc.add_paragraph()
        _shade_paragraph(text_p, "F4F6F8")
        _add_full_border(text_p, primary_hex)
        text_p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        text_run = text_p.add_run(block.get("text", ""))
        text_run.italic = True
        text_run.font.size = Pt(11)
        doc.add_paragraph().paragraph_format.space_after = Pt(4)  # small gap after the box

    elif block_type == "table":
        headers = block.get("headers", [])
        rows = block.get("rows", [])
        if headers:
            table = doc.add_table(rows=1 + len(rows), cols=len(headers))
            table.style = "Table Grid"
            for i, h in enumerate(headers):
                cell = table.cell(0, i)
                cell.text = h
                cell.paragraphs[0].runs[0].bold = True
                cell.paragraphs[0].runs[0].font.size = Pt(10)
            for r, row in enumerate(rows):
                for c, value in enumerate(row):
                    if c < len(headers):
                        table.cell(r + 1, c).text = str(value)
                        for run in table.cell(r + 1, c).paragraphs[0].runs:
                            run.font.size = Pt(10)
            doc.add_paragraph().paragraph_format.space_after = Pt(4)

    elif block_type == "formula":
        formula_p = doc.add_paragraph()
        formula_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        formula_p.paragraph_format.space_before = Pt(8)
        _shade_paragraph(formula_p, "FFF8E7")
        if block.get("label"):
            label_run = formula_p.add_run(f"{block['label']}: ")
            label_run.bold = True
            label_run.font.size = Pt(11)
            label_run.font.color.rgb = secondary
        formula_run = formula_p.add_run(block.get("text", ""))
        formula_run.font.size = Pt(13)
        formula_run.font.name = "Consolas"

        variables = block.get("variables", [])
        if variables:
            legend_p = doc.add_paragraph()
            legend_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            _shade_paragraph(legend_p, "FFF8E7")
            legend_run = legend_p.add_run("Where:")
            legend_run.italic = True
            legend_run.font.size = Pt(10)
            legend_run.font.color.rgb = secondary
            for v in variables:
                var_run = legend_p.add_run(f"\n{v.get('symbol', '')} = {v.get('meaning', '')}")
                var_run.font.size = Pt(10)
        doc.add_paragraph().paragraph_format.space_after = Pt(4)

    elif block_type == "example_tip":
        # Derive light tint shades from the org's actual brand colors instead of hardcoded hex —
        # a very light version of primary for the example side, accent for the tip side
        def _lighten(hex_color, factor=0.88):
            hex_color = hex_color.lstrip("#")
            r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
            r = int(r + (255 - r) * factor)
            g = int(g + (255 - g) * factor)
            b = int(b + (255 - b) * factor)
            return f"{r:02X}{g:02X}{b:02X}"

        example_shade = _lighten(primary_hex)
        tip_shade = _lighten(accent_hex or "F39C12")

        table = doc.add_table(rows=1, cols=2)
        table.autofit = True
        left_cell, right_cell = table.rows[0].cells

        left_para = left_cell.paragraphs[0]
        _shade_paragraph(left_para, example_shade)
        left_label = left_para.add_run("Practical Example\n")
        left_label.bold = True
        left_label.font.size = Pt(10)
        left_label.font.color.rgb = secondary
        left_body = left_para.add_run(block.get("example", ""))
        left_body.font.size = Pt(10)
        left_body.italic = True

        right_para = right_cell.paragraphs[0]
        _shade_paragraph(right_para, tip_shade)
        right_label = right_para.add_run("Helpful Tip\n")
        right_label.bold = True
        right_label.font.size = Pt(10)
        right_label.font.color.rgb = secondary
        right_body = right_para.add_run(block.get("tip", ""))
        right_body.font.size = Pt(10)
        right_body.italic = True

        doc.add_paragraph().paragraph_format.space_after = Pt(6)

    elif block_type == "exercise":
        box_para = doc.add_paragraph()
        _shade_paragraph(box_para, "F4F6F8")
        _add_full_border(box_para, primary_hex)
        title_run = box_para.add_run("Exercise Time!\n")
        title_run.bold = True
        title_run.font.size = Pt(11)
        title_run.font.color.rgb = secondary

        scenario_run = box_para.add_run("Scenario: ")
        scenario_run.bold = True
        scenario_run.font.size = Pt(10)
        box_para.add_run(f"{block.get('scenario', '')}\n")

        task_run = box_para.add_run("Task: ")
        task_run.bold = True
        task_run.font.size = Pt(10)
        box_para.add_run(f"{block.get('task', '')}\n")

        for q in block.get("questions", []):
            q_run = box_para.add_run(f"• {q}\n")
            q_run.font.size = Pt(10)

        doc.add_paragraph().paragraph_format.space_after = Pt(6)

    elif block_type == "info_box":
        box_para = doc.add_paragraph()
        box_para.paragraph_format.space_before = Pt(6)
        _shade_paragraph(box_para, "F4F6F8")  # light neutral tint — background stays subtle, text/border carry the brand
        _add_full_border(box_para, primary_hex)
        if block.get("title"):
            title_run = box_para.add_run(block["title"] + "\n")
            title_run.bold = True
            title_run.font.size = Pt(11)
            title_run.font.color.rgb = secondary
        items = block.get("items", [])
        if items:
            for item in items:
                item_run = box_para.add_run(f"• {item}\n")
                item_run.font.size = Pt(10)
        elif block.get("text"):
            text_run = box_para.add_run(block["text"])
            text_run.font.size = Pt(10)
        doc.add_paragraph().paragraph_format.space_after = Pt(4)

    elif block_type == "diagram":
        from app.services.image_service import generate_flow_diagram
        steps = block.get("steps", [])
        if steps:
            try:
                png_bytes = generate_flow_diagram(steps, primary_hex=primary_hex, accent_hex=accent_hex or "F39C12")
                img_para = doc.add_paragraph()
                img_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
                img_para.add_run().add_picture(io.BytesIO(png_bytes), width=Inches(4.5))
                if block.get("caption"):
                    cap_para = doc.add_paragraph()
                    cap_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
                    cap_run = cap_para.add_run(block["caption"])
                    cap_run.italic = True
                    cap_run.font.size = Pt(9)
            except Exception as exc:
                print(f"[DEBUG] diagram render failed: {exc}")

    elif block_type == "model_diagram":
        from app.services.model_diagram_service import generate_model_diagram
        _seen = getattr(doc, "_seen_model_diagrams", None)
        if _seen is None:
            _seen = set()
            try:
                doc._seen_model_diagrams = _seen
            except Exception:
                pass
        _items = block.get("items") or []
        _first = (_items[0].get("label", "") if _items and isinstance(_items[0], dict) else "")
        _key = ((block.get("title") or "") or _first).strip().lower()
        _dup = bool(_key) and _key in _seen
        if _key:
            _seen.add(_key)
        try:
            png_bytes = None if _dup else generate_model_diagram(
                block.get("kind", ""), block.get("items") or [], block.get("title", ""),
                primary_hex=primary_hex, accent_hex=accent_hex or "F39C12", axes=block.get("axes"),
            )
            if png_bytes:
                img_para = doc.add_paragraph()
                img_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
                img_para.add_run().add_picture(io.BytesIO(png_bytes), width=Inches(5.0))
                if block.get("caption"):
                    cap_para = doc.add_paragraph()
                    cap_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
                    cap_run = cap_para.add_run(block["caption"])
                    cap_run.italic = True
                    cap_run.font.size = Pt(9)
            else:
                print(f"[DEBUG] model_diagram skipped (unusable data): kind={block.get('kind')!r}")
        except Exception as exc:
            print(f"[DEBUG] model_diagram render failed: {exc}")

    elif block_type == "image":
        from app.services.image_service import fetch_stock_photo
        search_term = block.get("search_term", "")
        print(f"[DEBUG] image block search_term: '{search_term}'")
        if search_term:
            try:
                photo_bytes = fetch_stock_photo(search_term)
                print(f"[DEBUG] photo_bytes returned: {photo_bytes is not None}")
                if photo_bytes:
                    img_para = doc.add_paragraph()
                    img_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
                    img_para.add_run().add_picture(io.BytesIO(photo_bytes), width=Inches(4.5))
                    if block.get("caption"):
                        cap_para = doc.add_paragraph()
                        cap_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
                        cap_run = cap_para.add_run(block["caption"])
                        cap_run.italic = True
                        cap_run.font.size = Pt(9)
            except Exception as exc:
                print(f"[DEBUG] image render failed: {exc}")

    elif block_type == "list":
        items = block.get("items", [])
        ordered = block.get("ordered", False)
        if ordered:
            for item_i, item in enumerate(items, start=1):
                doc.add_paragraph(f"{item_i}. {item}")
        else:
            for item in items:
                doc.add_paragraph(item, style="List Bullet")
        doc.add_paragraph().paragraph_format.space_after = Pt(4)

    else:  # paragraph
        for para_text in block.get("text", "").split("\n\n"):
            cleaned = para_text.strip()
            if cleaned:
                body_p = doc.add_paragraph(cleaned)
                body_p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
                body_p.paragraph_format.space_after = Pt(8)


def _shade_paragraph(paragraph, color_hex: str):
    """Adds a background fill color behind a paragraph — used for the org-name band on the cover."""
    p_pr = paragraph._p.get_or_add_pPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), color_hex.lstrip("#").upper())
    p_pr.append(shd)


def _add_page_border(section, color_hex: str):
    """Adds a decorative border around the entire page — applies to the whole section (page)."""
    sect_pr = section._sectPr
    p_borders = OxmlElement("w:pgBorders")
    p_borders.set(qn("w:offsetFrom"), "page")
    for edge in ("top", "left", "bottom", "right"):
        border = OxmlElement(f"w:{edge}")
        border.set(qn("w:val"), "single")
        border.set(qn("w:sz"), "24")
        border.set(qn("w:space"), "24")
        border.set(qn("w:color"), color_hex.lstrip("#").upper())
        p_borders.append(border)
    sect_pr.append(p_borders)


def _set_default_font(doc: Document, font_name: str = "Calibri"):
    style = doc.styles["Normal"]
    style.font.name = font_name or "Calibri"
    style.font.size = Pt(11)
    style.paragraph_format.line_spacing = 1.0
    style.paragraph_format.space_before = Pt(0)
    style.paragraph_format.space_after = Pt(0)
    # East Asian font element must also be set, or Word silently falls back to Calibri
    # for the "Normal" style's complex-script/east-asian font in some Word versions.
    rpr = style.element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.append(rfonts)
    rfonts.set(qn("w:eastAsia"), font_name or "Calibri")


def build_textbook_docx(title: str, units: list, organization_name: str = None,
                         seta: str = None, nqf_level: str = None, logo_bytes: bytes = None,
                         brand_colors: dict = None, job_id: str = None,
                         accreditation_info: dict = None, **kwargs) -> BytesIO:
    accreditation_info = accreditation_info or {}
    brand_colors = brand_colors or {}
    primary_hex = brand_colors.get("primary", DEFAULT_PRIMARY).lstrip("#") if brand_colors.get("primary") else DEFAULT_PRIMARY
    secondary_hex = brand_colors.get("secondary", DEFAULT_SECONDARY).lstrip("#") if brand_colors.get("secondary") else DEFAULT_SECONDARY
    accent_hex = brand_colors.get("accent", DEFAULT_ACCENT).lstrip("#") if brand_colors.get("accent") else DEFAULT_ACCENT

    primary = _hex_to_rgb(primary_hex, DEFAULT_PRIMARY)
    secondary = _hex_to_rgb(secondary_hex, DEFAULT_SECONDARY)
    accent = _hex_to_rgb(accent_hex, DEFAULT_ACCENT)

    doc = Document()

    _set_default_font(doc, brand_colors.get("font"))

    # Decorative border around the whole cover page
    _add_page_border(doc.sections[0], primary_hex)

    # Vertical spacing to center the cover content
    for _ in range(4):
        doc.add_paragraph()
    if logo_bytes:
        logo_para = doc.add_paragraph()
        logo_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = logo_para.add_run()
        run.add_picture(BytesIO(logo_bytes), width=Inches(1.8))
        _add_watermark(doc, logo_bytes)

    doc.add_paragraph()

    # Thin accent rule above the title
    rule_above = doc.add_paragraph()
    rule_above.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _add_bottom_border(rule_above, accent_hex, size="10")

    title_para = doc.add_paragraph()
    title_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title_run = title_para.add_run(title)
    title_run.bold = True
    title_run.font.size = Pt(32)
    title_run.font.color.rgb = primary
    title_run.font.name = "Calibri"

    # Accent rule below the title
    rule_below = doc.add_paragraph()
    rule_below.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _add_bottom_border(rule_below, accent_hex, size="10")

    doc.add_paragraph()

    if organization_name:
        # Shaded band behind the org name for visual weight
        org_para = doc.add_paragraph()
        org_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
        org_para.paragraph_format.space_before = Pt(6)
        org_para.paragraph_format.space_after = Pt(6)
        _shade_paragraph(org_para, primary_hex)
        org_run = org_para.add_run(f"  {organization_name}  ")
        org_run.font.size = Pt(16)
        org_run.bold = True
        org_run.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)  # white text on the colored band

    doc.add_paragraph()
    subtitle_para = doc.add_paragraph()
    subtitle_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    subtitle_run = subtitle_para.add_run("Workplace Training Material")
    subtitle_run.italic = True
    subtitle_run.font.size = Pt(12)
    subtitle_run.font.color.rgb = secondary

    doc.add_paragraph()
    details_heading = doc.add_paragraph()
    details_heading.add_run("Learner Details").bold = True
    details_table = doc.add_table(rows=5, cols=2)
    details_table.style = "Table Grid"
    for i, field in enumerate(["Learner Name", "Learner ID Number", "Facilitator Name", "Date Issued", "Signature"]):
        details_table.cell(i, 0).text = field
        details_table.cell(i, 0).paragraphs[0].runs[0].bold = True

    doc.add_paragraph()
    instructions_heading = doc.add_paragraph()
    instructions_heading.add_run("How to Use This Textbook").bold = True
    doc.add_paragraph(
        "This textbook is structured into units, each covering a distinct area of the "
        "qualification. Work through each unit in order, completing any activities or "
        "exercises included, and use the Table of Contents to navigate between sections."
    )

    doc.add_page_break()

    # Table of contents
    toc_heading = doc.add_paragraph()
    toc_run = toc_heading.add_run("Table of Contents")
    toc_run.bold = True
    toc_run.font.size = Pt(20)
    toc_run.font.color.rgb = primary
    _add_bottom_border(toc_heading, primary_hex)

    for i, unit in enumerate(units, start=1):
        p = doc.add_paragraph()
        run = p.add_run(f"{i}.  {unit.get('name', f'Unit {i}')}")
        run.font.size = Pt(12)
        run.font.color.rgb = secondary
    doc.add_page_break()

    for i, unit in enumerate(units, start=1):
        unit_name = unit.get("name", f"Unit {i}")
        outcomes = unit.get("outcomes", [])

        chapter_heading = doc.add_paragraph()
        chapter_run = chapter_heading.add_run(unit_name)
        chapter_run.bold = True
        chapter_run.font.size = Pt(22)
        chapter_run.font.color.rgb = primary
        _add_bottom_border(chapter_heading, primary_hex)
        doc.add_paragraph()

        outcomes_heading = doc.add_paragraph()
        outcomes_run = outcomes_heading.add_run("LEARNING OUTCOMES")
        outcomes_run.bold = True
        outcomes_run.underline = True
        outcomes_run.font.size = Pt(13)
        outcomes_run.font.color.rgb = accent

        for outcome in outcomes:
            doc.add_paragraph(outcome, style="List Bullet")

        doc.add_paragraph()

        chapter = write_chapter_content(unit_name, outcomes, course_title=title, seta=seta, nqf_level=nqf_level, job_id=job_id)

        if chapter.get("intro"):
            intro_p = doc.add_paragraph()
            intro_p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
            intro_run = intro_p.add_run(chapter["intro"])
            intro_run.italic = True
            intro_run.font.size = Pt(12)

        for section in chapter.get("sections", []):
            heading = section.get("heading", "")
            if heading:
                section_heading = doc.add_paragraph()
                section_run = section_heading.add_run(heading)
                section_run.bold = True
                section_run.font.size = Pt(15)
                section_run.font.color.rgb = secondary

            blocks = section.get("blocks")
            if blocks:
                for block in blocks:
                    _render_content_block(doc, block, primary_hex, secondary, accent_hex=accent_hex)
            else:
                # Fallback for any older-format response that still uses "body" instead of "blocks"
                body = section.get("body", "")
                for para in body.split("\n\n"):
                    cleaned = para.strip()
                    if cleaned:
                        body_p = doc.add_paragraph(cleaned)
                        body_p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
                        body_p.paragraph_format.space_after = Pt(8)

        key_points = chapter.get("key_points", [])
        if key_points:
            kp_heading = doc.add_paragraph()
            kp_run = kp_heading.add_run("KEY POINTS")
            kp_run.bold = True
            kp_run.underline = True
            kp_run.font.size = Pt(13)
            kp_run.font.color.rgb = accent
            for point in key_points:
                doc.add_paragraph(point, style="List Bullet")

        doc.add_page_break()

    _add_signature_block(doc)
    _add_branded_header_footer(
        doc, logo_bytes=logo_bytes, qualification_name=title,
        organization_name=organization_name, primary_hex=primary_hex,
        watermark=False, accreditation_info=accreditation_info, document_label="Textbook",
    )

    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    return buffer

def _add_toc_field(doc):
    """Inserts a real Word Table of Contents field, scanning Heading 1-3 styled
    paragraphs and generating hyperlinked entries with real page numbers — unlike a
    hardcoded list of section names, this is an actual Word field. It will show a
    placeholder until the document is opened in Word and the field is updated
    (right-click -> Update Field, or Word may prompt automatically on open) — python-docx
    has no way to know pagination in advance, since that only happens when Word actually
    lays out the document."""
    from docx.oxml.ns import qn as _qn
    paragraph = doc.add_paragraph()
    run = paragraph.add_run()

    fld_begin = OxmlElement("w:fldChar")
    fld_begin.set(_qn("w:fldCharType"), "begin")
    fld_begin.set(_qn("w:dirty"), "true")

    instr_text = OxmlElement("w:instrText")
    instr_text.set(_qn("xml:space"), "preserve")
    instr_text.text = 'TOC \\o "1-3" \\h \\z \\u'

    fld_separate = OxmlElement("w:fldChar")
    fld_separate.set(_qn("w:fldCharType"), "separate")

    placeholder_run_text = OxmlElement("w:t")
    placeholder_run_text.text = "Right-click and select 'Update Field' to generate the Table of Contents."

    fld_end = OxmlElement("w:fldChar")
    fld_end.set(_qn("w:fldCharType"), "end")

    r_element = run._r
    r_element.append(fld_begin)
    r_element.append(instr_text)
    r_element.append(fld_separate)
    r_element.append(placeholder_run_text)
    r_element.append(fld_end)

    return paragraph

def _add_page_numbers(doc: Document):
    """Adds 'Page X of Y' to the footer of every section — a real Word field, not static text."""
    from docx.oxml.ns import qn as _qn
    for section in doc.sections:
        footer = section.footer
        footer.is_linked_to_previous = False
        para = footer.paragraphs[0] if footer.paragraphs else footer.add_paragraph()
        para.alignment = WD_ALIGN_PARAGRAPH.CENTER
        para.text = ""

        run = para.add_run("Page ")

        def _add_field(paragraph, field_code):
            run_el = OxmlElement("w:r")
            rPr = OxmlElement("w:rPr")
            sz = OxmlElement("w:sz")
            sz.set(_qn("w:val"), "18")
            rPr.append(sz)
            run_el.append(rPr)
            fld_begin = OxmlElement("w:fldChar")
            fld_begin.set(_qn("w:fldCharType"), "begin")
            instr = OxmlElement("w:instrText")
            instr.set(_qn("xml:space"), "preserve")
            instr.text = field_code
            fld_end = OxmlElement("w:fldChar")
            fld_end.set(_qn("w:fldCharType"), "end")
            run_el.append(fld_begin)
            run_el.append(instr)
            run_el.append(fld_end)
            paragraph._p.append(run_el)

        _add_field(para, "PAGE")
        para.add_run(" of ")
        _add_field(para, "NUMPAGES")
def _add_watermark(doc: Document, logo_bytes: bytes, width_inches: float = 4.2):
    """Adds the organization logo as a large, washed-out watermark centered on every page.
    Uses the legacy VML <w:pict> markup in the header rather than a hand-built DrawingML
    anchor — this is what Word's own 'Insert Watermark > Picture Watermark' feature actually
    generates, and renders far more reliably across Word versions than a floating DrawingML
    picture built from scratch. gain/blacklevel on v:imagedata replicate the washed-out look."""
    if not logo_bytes:
        return

    # VML namespaces aren't in python-docx's default prefix map — register them once so
    # qn("v:...") / qn("o:...") resolve. Safe no-op on repeat calls (setdefault).
    from docx.oxml.ns import nsmap as _nsmap
    _nsmap.setdefault("v", "urn:schemas-microsoft-com:vml")
    _nsmap.setdefault("o", "urn:schemas-microsoft-com:office:office")

    section = doc.sections[0]
    header = section.header
    header.is_linked_to_previous = False
    # Dedicated paragraph for the watermark, separate from the header's logo/qualification-name
    # paragraph — sharing a paragraph caused both pictures to get the same docPr id, which made
    # Word silently drop one of them.
    watermark_para = header.add_paragraph()
    watermark_para.alignment = WD_ALIGN_PARAGRAPH.CENTER

    run = watermark_para.add_run()
    run.add_picture(BytesIO(logo_bytes), width=Inches(width_inches))

    # add_picture() creates a modern <w:drawing> (DrawingML); pull the relationship id it
    # just created for the embedded image, then swap the drawing for the legacy VML <w:pict>
    # watermark markup, reusing that same image relationship.
    drawing = run._element.find(qn("w:drawing"))
    blip = drawing.find(f".//{qn('a:blip')}")
    r_id = blip.get(qn("r:embed"))

    width_pt = int(width_inches * 72)

    pict = OxmlElement("w:pict")
    shape = OxmlElement("v:shape")
    shape.set("id", "WatermarkShape")
    shape.set("type", "#_x0000_t75")
    shape.set("style", (
        f"position:absolute;left:0;text-align:left;margin-left:0;margin-top:0;"
        f"width:{width_pt}pt;height:{width_pt}pt;z-index:-251658240;"
        f"mso-position-horizontal:center;mso-position-horizontal-relative:margin;"
        f"mso-position-vertical:center;mso-position-vertical-relative:margin"
    ))
    shape.set(qn("o:allowoverlap"), "f")

    imagedata = OxmlElement("v:imagedata")
    imagedata.set(qn("r:id"), r_id)
    imagedata.set(qn("o:title"), "")
    imagedata.set("gain", "19661f")
    imagedata.set("blacklevel", "22938f")

    shape.append(imagedata)
    pict.append(shape)

    run._element.remove(drawing)
    run._element.append(pict)


def _add_branded_header_footer(doc: Document, logo_bytes: bytes = None, qualification_name: str = None,
                                organization_name: str = None, primary_hex: str = None,
                                watermark: bool = True, accreditation_info: dict = None,
                                document_label: str = None):
    """Full branded page treatment applied once, reused across every document type: a small
    logo + qualification name in the header with a thin rule, 'Organization — Page X of Y' in
    the footer, and (optionally) the organization logo as a faint watermark behind the text.
    Superset of _add_page_numbers — call this instead when logo/qualification context is
    available; falls back gracefully to page-numbers-only if logo_bytes/qualification_name
    aren't supplied. When accreditation_info contains a recognized "seta" slug and that
    SETA's logo file exists, the header instead shows a second logo (the SETA's) on the
    opposite side from the organization's logo, with centered text between them showing
    the SETA name, qualification name, document type, qualification code, SAQA ID (if
    present), and NQF level. Callers that don't pass accreditation_info/document_label get
    the original single-logo layout, unchanged."""
    section = doc.sections[0]
    color_hex = (primary_hex or DEFAULT_PRIMARY).lstrip("#").upper()

    # Cover page (page 1) gets none of this — matches the reference material, where the
    # cover has no footer bar or header logo, only content pages from page 2 onward do.
    section.different_first_page_header_footer = True

    accreditation_info = accreditation_info or {}
    seta_slug = accreditation_info.get("seta")
    seta_logo_bytes = None
    seta_name = None
    if seta_slug:
        from app.services.seta_constants import get_seta_name, get_seta_logo_path
        seta_logo_path = get_seta_logo_path(seta_slug)
        if seta_logo_path and os.path.exists(seta_logo_path):
            with open(seta_logo_path, "rb") as f:
                seta_logo_bytes = f.read()
        seta_name = get_seta_name(seta_slug)

    if logo_bytes or qualification_name or seta_logo_bytes:
        header = section.header
        header.is_linked_to_previous = False
        header_para = header.paragraphs[0] if header.paragraphs else header.add_paragraph()
        header_para.text = ""

        if seta_logo_bytes:
            # Two-column-text-plus-images layout via a borderless table — a plain paragraph
            # with tab stops can't reliably center content between two images of different
            # widths, so a 3-column table gives precise control: org logo | centered text |
            # SETA logo.
            header_table = header.add_table(rows=1, cols=3, width=Inches(6.5))
            header_table.autofit = False
            header_table.columns[0].width = Inches(1.2)
            header_table.columns[1].width = Inches(4.1)
            header_table.columns[2].width = Inches(1.2)
            for row in header_table.rows:
                for cell in row.cells:
                    tcPr = cell._tc.get_or_add_tcPr()
                    borders = OxmlElement("w:tcBorders")
                    for edge in ("top", "left", "bottom", "right"):
                        edge_el = OxmlElement(f"w:{edge}")
                        edge_el.set(qn("w:val"), "nil")
                        borders.append(edge_el)
                    tcPr.append(borders)

            left_cell, center_cell, right_cell = header_table.rows[0].cells

            if logo_bytes:
                left_p = left_cell.paragraphs[0]
                left_p.alignment = WD_ALIGN_PARAGRAPH.LEFT
                left_run = left_p.add_run()
                left_run.add_picture(BytesIO(logo_bytes), height=Inches(0.25))

            center_p = center_cell.paragraphs[0]
            center_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            center_lines = []
            if seta_name:
                center_lines.append(seta_name)
            if qualification_name:
                center_lines.append(qualification_name)
            if document_label:
                center_lines.append(document_label)
            code_parts = []
            if accreditation_info.get("qualification_code"):
                code_parts.append(str(accreditation_info["qualification_code"]))
            if accreditation_info.get("saqa_id"):
                code_parts.append(f"SAQA ID: {accreditation_info['saqa_id']}")
            if accreditation_info.get("nqf_level"):
                code_parts.append(f"NQF {accreditation_info['nqf_level']}")
            if code_parts:
                center_lines.append(" | ".join(code_parts))

            for i, line in enumerate(center_lines):
                p = center_p if i == 0 else center_cell.add_paragraph()
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                p.paragraph_format.space_before = Pt(0)
                p.paragraph_format.space_after = Pt(0)
                run = p.add_run(line)
                run.font.size = Pt(7 if i > 0 else 8)
                run.bold = (i == 0)
                run.font.color.rgb = _hex_to_rgb(color_hex, DEFAULT_PRIMARY)

            right_p = right_cell.paragraphs[0]
            right_p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
            right_run = right_p.add_run()
            right_run.add_picture(BytesIO(seta_logo_bytes), height=Inches(0.25))

            _add_bottom_border(header_para, color_hex, size="6")
        else:
            # Original single-logo-plus-qualification-name layout — unchanged, for callers
            # that haven't been updated to pass accreditation_info/document_label yet.
            header_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
            if logo_bytes:
                logo_run = header_para.add_run()
                logo_run.add_picture(BytesIO(logo_bytes), height=Inches(0.45))
                header_para.add_run("   ")
            if qualification_name:
                qual_run = header_para.add_run(qualification_name)
                qual_run.bold = True
                qual_run.font.size = Pt(10)
                qual_run.font.color.rgb = _hex_to_rgb(color_hex, DEFAULT_PRIMARY)
            _add_bottom_border(header_para, color_hex, size="6")

    # Footer: organization name (left) + Page X of Y (right), on one line via tab stops
    footer = section.footer
    footer.is_linked_to_previous = False
    footer_para = footer.paragraphs[0] if footer.paragraphs else footer.add_paragraph()
    footer_para.text = ""
    from docx.enum.text import WD_TAB_ALIGNMENT
    footer_para.paragraph_format.tab_stops.add_tab_stop(Inches(6.5), WD_TAB_ALIGNMENT.RIGHT)

    if organization_name:
        org_run = footer_para.add_run(organization_name)
        org_run.font.size = Pt(9)
        org_run.font.color.rgb = _hex_to_rgb(color_hex, DEFAULT_PRIMARY)
        contact_bits = [p for p in [
            accreditation_info.get("organization_address"),
            accreditation_info.get("organization_phone"),
            accreditation_info.get("organization_email"),
            accreditation_info.get("organization_website"),
        ] if p]
        if contact_bits:
            contact_run = footer_para.add_run("  ·  " + "  ·  ".join(contact_bits))
            contact_run.font.size = Pt(7)
            contact_run.font.color.rgb = _hex_to_rgb(color_hex, DEFAULT_PRIMARY)

    footer_para.add_run("\t")

    from docx.oxml.ns import qn as _qn

    def _add_field(paragraph, field_code):
        run_el = OxmlElement("w:r")
        rPr = OxmlElement("w:rPr")
        sz = OxmlElement("w:sz")
        sz.set(_qn("w:val"), "18")
        rPr.append(sz)
        run_el.append(rPr)
        fld_begin = OxmlElement("w:fldChar")
        fld_begin.set(_qn("w:fldCharType"), "begin")
        instr = OxmlElement("w:instrText")
        instr.set(_qn("xml:space"), "preserve")
        instr.text = field_code
        fld_end = OxmlElement("w:fldChar")
        fld_end.set(_qn("w:fldCharType"), "end")
        run_el.append(fld_begin)
        run_el.append(instr)
        run_el.append(fld_end)
        paragraph._p.append(run_el)

    page_label_run = footer_para.add_run("Page ")
    page_label_run.font.size = Pt(9)
    _add_field(footer_para, "PAGE")
    of_run = footer_para.add_run(" of ")
    of_run.font.size = Pt(9)
    _add_field(footer_para, "NUMPAGES")

    if watermark and logo_bytes:
        _add_watermark(doc, logo_bytes)


def _build_branded_cover(doc: Document, doc_title: str, doc_subtitle: str, organization_name: str,
                          logo_bytes: bytes, primary, primary_hex: str, secondary, accent_hex: str = None):
    """Shared branded cover page used by every document type: full-width top and bottom
    accent bands, full page border, centered logo, bold title, colored accent rules, a
    shaded organization name band, and a learner/facility details table -- designed to
    use the full page rather than leaving the lower half blank."""
    accent_hex = accent_hex or primary_hex
    _add_page_border(doc.sections[0], primary_hex)

    top_band = doc.add_paragraph()
    top_band.alignment = WD_ALIGN_PARAGRAPH.CENTER
    top_band.paragraph_format.space_before = Pt(0)
    top_band.paragraph_format.space_after = Pt(0)
    _shade_paragraph(top_band, accent_hex)
    top_run = top_band.add_run("A C C R E D I T E D   T R A I N I N G   M A T E R I A L")
    top_run.bold = True
    top_run.font.size = Pt(10)
    top_run.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)

    for _ in range(3):
        doc.add_paragraph()

    if logo_bytes:
        logo_para = doc.add_paragraph()
        logo_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
        logo_para.add_run().add_picture(BytesIO(logo_bytes), width=Inches(1.6))
        doc.add_paragraph()

    rule_above = doc.add_paragraph()
    rule_above.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _add_bottom_border(rule_above, accent_hex, size="10")

    title_para = doc.add_paragraph()
    title_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title_run = title_para.add_run(doc_title)
    title_run.bold = True
    title_run.font.size = Pt(28)
    title_run.font.color.rgb = primary

    if doc_subtitle:
        subtitle_para = doc.add_paragraph()
        subtitle_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
        subtitle_run = subtitle_para.add_run(doc_subtitle)
        subtitle_run.italic = True
        subtitle_run.font.size = Pt(14)
        subtitle_run.font.color.rgb = secondary

    rule_below = doc.add_paragraph()
    rule_below.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _add_bottom_border(rule_below, accent_hex, size="10")

    doc.add_paragraph()

    if organization_name:
        org_para = doc.add_paragraph()
        org_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
        org_para.paragraph_format.space_before = Pt(6)
        org_para.paragraph_format.space_after = Pt(6)
        _shade_paragraph(org_para, primary_hex)
        org_run = org_para.add_run(f"  {organization_name}  ")
        org_run.font.size = Pt(15)
        org_run.bold = True
        org_run.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)

    doc.add_paragraph()
    _add_cover_details_table(doc, primary, accent_hex)

    doc.add_paragraph()
    doc.add_paragraph()

    tagline_para = doc.add_paragraph()
    tagline_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    tagline_run = tagline_para.add_run(
        "Curriculum Training Material"
    )
    tagline_run.italic = True
    tagline_run.font.size = Pt(9)
    tagline_run.font.color.rgb = secondary

    for _ in range(6):
        doc.add_paragraph()

    bottom_band = doc.add_paragraph()
    bottom_band.alignment = WD_ALIGN_PARAGRAPH.CENTER
    bottom_band.paragraph_format.space_before = Pt(0)
    bottom_band.paragraph_format.space_after = Pt(0)
    _shade_paragraph(bottom_band, primary_hex)
    bottom_run = bottom_band.add_run("PREPARED FOR INTERNAL TRAINING USE")
    bottom_run.bold = True
    bottom_run.font.size = Pt(9)
    bottom_run.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)

    doc.add_page_break()

def _center_table(table):
    """Centers a table on the page. python-docx has no WD_TABLE_ALIGNMENT import
    already in this file, so this sets the underlying <w:jc> directly."""
    tbl_pr = table._tbl.tblPr
    jc = OxmlElement("w:jc")
    jc.set(qn("w:val"), "center")
    tbl_pr.append(jc)


def _add_cover_details_table(doc: Document, primary, accent_hex: str):
    """Compact fill-in-by-hand block on the cover page recording who this pack
    belongs to and where/when it was issued."""
    rule_above = doc.add_paragraph()
    rule_above.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _add_bottom_border(rule_above, accent_hex, size="4")

    heading = doc.add_paragraph()
    heading.alignment = WD_ALIGN_PARAGRAPH.CENTER
    h_run = heading.add_run("Learner / Facility Details")
    h_run.bold = True
    h_run.font.size = Pt(12)
    h_run.font.color.rgb = primary

    fields = [
        "Learner Name",
        "Learner / ID Number",
        "Training Provider / Facility Name",
        "Facilitator / Assessor Name",
        "SETA / Qualification Code",
        "Date Issued",
    ]

    table = doc.add_table(rows=len(fields), cols=2)
    table.style = "Table Grid"
    table.autofit = False
    _center_table(table)
    for i, label in enumerate(fields):
        table.columns[0].width = Inches(2.4)
        table.columns[1].width = Inches(3.4)
        label_cell = table.cell(i, 0)
        label_cell.width = Inches(2.4)
        label_cell.text = label
        label_cell.paragraphs[0].runs[0].bold = True
        label_cell.paragraphs[0].runs[0].font.size = Pt(10)
        value_cell = table.cell(i, 1)
        value_cell.width = Inches(3.4)
        value_cell.text = ""

    doc.add_paragraph()
    rule_below = doc.add_paragraph()
    rule_below.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _add_bottom_border(rule_below, accent_hex, size="4")

def _add_hyperlink(paragraph, url, text, color_hex="0563C1"):
    """Adds a real, clickable hyperlink to a paragraph — python-docx has no built-in
    hyperlink support, so this constructs the underlying XML relationship directly."""
    part = paragraph.part
    r_id = part.relate_to(url, "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink", is_external=True)

    hyperlink = OxmlElement("w:hyperlink")
    hyperlink.set(qn("r:id"), r_id)

    new_run = OxmlElement("w:r")
    rPr = OxmlElement("w:rPr")

    color = OxmlElement("w:color")
    color.set(qn("w:val"), color_hex)
    rPr.append(color)

    underline = OxmlElement("w:u")
    underline.set(qn("w:val"), "single")
    rPr.append(underline)

    new_run.append(rPr)
    text_elem = OxmlElement("w:t")
    text_elem.text = text
    new_run.append(text_elem)
    hyperlink.append(new_run)

    paragraph._p.append(hyperlink)

def _add_document_control_copyright(doc: Document, primary: RGBColor, primary_hex: str,
                                     qualification_title: str = None, qualification_code: str = None,
                                     saqa_id: str = None, nqf_level: str = None, credits=None,
                                     seta_name: str = None, modules_covered: str = None,
                                     organization_name: str = None, document_title: str = None,
                                     organization_address: str = None, organization_phone: str = None,
                                     organization_email: str = None, organization_website: str = None):
    """Adds a Document Control and Copyright page — placed right after the cover page,
    before the Table of Contents. Only fields with real, available data are shown; fields
    the system has no source for (version, date of issue, developed by, approved by) are
    left as blank fill-in lines rather than invented."""
    heading = doc.add_paragraph()
    heading_run = heading.add_run("Document Control and Copyright")
    heading_run.bold = True
    heading_run.font.size = Pt(16)
    heading_run.font.color.rgb = primary
    _add_bottom_border(heading, primary_hex, size="8")

    table = doc.add_table(rows=0, cols=2)
    table.style = "Table Grid"

    def add_row(label, value):
        row = table.add_row()
        row.cells[0].text = label
        row.cells[0].paragraphs[0].runs[0].bold = True
        row.cells[1].text = str(value) if value else ""

    if document_title:
        add_row("Document title", document_title)
    if qualification_title:
        add_row("Qualification", qualification_title)
    if qualification_code:
        add_row("Qualification code", qualification_code)
    if saqa_id:
        add_row("SAQA identifier", saqa_id)
    if nqf_level:
        credits_part = f" · {credits} credits" if credits else ""
        add_row("NQF level and credits", f"NQF Level {nqf_level}{credits_part}")
    if seta_name:
        add_row("Quality Partner", seta_name)
    if modules_covered:
        add_row("Modules covered", modules_covered)
    if organization_name:
        add_row("Training provider", organization_name)
    if organization_address:
        add_row("Provider address", organization_address)
    contact_parts = [p for p in [organization_phone, organization_email, organization_website] if p]
    if contact_parts:
        add_row("Provider contact", " · ".join(contact_parts))
    add_row("Version", "")
    add_row("Date of issue", "")
    add_row("Review date", "")
    add_row("Developed by", "")
    add_row("Approved by", "")

    doc.add_paragraph()
    copyright_heading = doc.add_paragraph()
    copyright_heading.add_run("Copyright").bold = True
    doc.add_paragraph(
        f"This material is the property of {organization_name or 'the training provider'}. "
        "It may be reproduced and used for the delivery of the qualification named above by "
        "this provider and its accredited delivery sites. It may not be sold, licensed, or "
        "reproduced for any other purpose without written permission. Curriculum content "
        "reproduced from the QCTO curriculum document is the intellectual property of the "
        "Quality Council for Trades and Occupations and is acknowledged as such."
    )

    doc.add_paragraph()
    note_heading = doc.add_paragraph()
    note_heading.add_run("A note on accuracy").bold = True
    doc.add_paragraph(
        "Legislation and standards cited in this material were current at the date of issue. "
        "Learners and facilitators must verify the current status of any provision before "
        "relying on it in practice. Where this material and a statute differ, the statute governs."
    )
    doc.add_page_break()
def _add_learner_registration_details(doc: Document, primary: RGBColor, primary_hex: str):
    """Condensed learner registration details page — based on the QCTO's official Learner
    Enrolment and Readiness for EISA data specification (32 fields across 6 parts),
    narrowed to the essential, non-duplicate fields and kept to roughly 2 pages. Shared
    across Learner Guides, POE documents, and other learner-facing material, so it isn't
    rebuilt or duplicated per document type."""
    heading = doc.add_paragraph()
    h_run = heading.add_run("Learner Registration Details")
    h_run.bold = True
    h_run.font.size = Pt(16)
    h_run.font.color.rgb = primary
    _add_bottom_border(heading, primary_hex)

    note = doc.add_paragraph()
    note.add_run(
        "Complete this page before your first contact session. This information is "
        "required by the QCTO for your enrolment record and is used for no other purpose."
    ).italic = True

    groups = [
        ("Personal Details", [
            "Title", "Surname", "First Name", "Middle Name (if any)",
            "South African ID Number", "Date of Birth (YYYYMMDD)",
            "Population Group", "Nationality", "Home Language", "Gender",
            "Citizen/Resident Status",
        ]),
        ("Address", [
            "Home Address", "Postal Address (if different)", "Postal Code", "Province",
        ]),
        ("Contact Details", [
            "Telephone Number", "Cellphone Number", "Email Address",
        ]),
        ("Additional Information", [
            "Socio-Economic Status", "Disability Status (if any)",
        ]),
        ("Consent", [
            "I agree to my personal information being used for enrolment, assessment and certification (Yes/No)",
            "Date Signed",
        ]),
    ]

    for group_name, fields in groups:
        gh = doc.add_paragraph()
        gh.add_run(group_name).bold = True
        gh.runs[0].font.size = Pt(11)
        table = doc.add_table(rows=0, cols=2)
        table.style = "Table Grid"
        for field in fields:
            row = table.add_row()
            row.cells[0].text = field
            row.cells[0].paragraphs[0].runs[0].bold = True
            row.cells[0].paragraphs[0].runs[0].font.size = Pt(10)
        doc.add_paragraph()

    doc.add_page_break()


def _add_signature_block(doc: Document):
    """Adds Learner/Facilitator/Assessor-Moderator signature lines — appended to every
    learner-facing document."""
    doc.add_paragraph()
    heading = doc.add_paragraph()
    heading.add_run("Sign-Off").bold = True
    for label in ["Learner Name & Signature:", "Date:", "Facilitator Name & Signature:", "Date:",
                  "Assessor / Moderator Name & Signature:", "Date:"]:
        p = doc.add_paragraph()
        p.add_run(f"{label} " + "_" * 40)
        p.paragraph_format.space_after = Pt(10)
