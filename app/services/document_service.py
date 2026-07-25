"""Builds a .docx textbook from structured syllabus content, styled with organization branding."""
from io import BytesIO
from docx import Document
from docx.shared import Pt, Inches, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
from app.services.ai_service import write_chapter_content
import io

DEFAULT_PRIMARY = "1A5276"
DEFAULT_SECONDARY = "2874A6"
DEFAULT_ACCENT = "F39C12"


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


def _render_content_block(doc, block, primary_hex, secondary):
    print(f"[DEBUG] block type received: {block.get('type')}")
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
        formula_p.paragraph_format.space_after = Pt(8)
        _shade_paragraph(formula_p, "FFF8E7")  # warm highlight background
        if block.get("label"):
            label_run = formula_p.add_run(f"{block['label']}: ")
            label_run.bold = True
            label_run.font.size = Pt(11)
        formula_run = formula_p.add_run(block.get("text", ""))
        formula_run.font.size = Pt(13)
        formula_run.font.name = "Consolas"

    elif block_type == "diagram":
        from app.services.image_service import generate_flow_diagram
        steps = block.get("steps", [])
        if steps:
            try:
                png_bytes = generate_flow_diagram(steps, primary_hex=primary_hex)
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


def _set_default_font(doc: Document):
    style = doc.styles["Normal"]
    style.font.name = "Calibri"
    style.font.size = Pt(11)


def build_textbook_docx(title: str, units: list, organization_name: str = None,
                         seta: str = None, nqf_level: str = None, logo_bytes: bytes = None,
                         brand_colors: dict = None, job_id: str = None) -> BytesIO:
    brand_colors = brand_colors or {}
    primary_hex = brand_colors.get("primary", DEFAULT_PRIMARY).lstrip("#") if brand_colors.get("primary") else DEFAULT_PRIMARY
    secondary_hex = brand_colors.get("secondary", DEFAULT_SECONDARY).lstrip("#") if brand_colors.get("secondary") else DEFAULT_SECONDARY
    accent_hex = brand_colors.get("accent", DEFAULT_ACCENT).lstrip("#") if brand_colors.get("accent") else DEFAULT_ACCENT

    primary = _hex_to_rgb(primary_hex, DEFAULT_PRIMARY)
    secondary = _hex_to_rgb(secondary_hex, DEFAULT_SECONDARY)
    accent = _hex_to_rgb(accent_hex, DEFAULT_ACCENT)

    doc = Document()
    _set_default_font(doc)

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

        chapter = write_chapter_content(unit_name, outcomes, seta=seta, nqf_level=nqf_level, job_id=job_id)

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
                    _render_content_block(doc, block, primary_hex, secondary)
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

    _add_page_numbers(doc)

    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    return buffer

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