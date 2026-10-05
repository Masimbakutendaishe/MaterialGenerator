"""Builds the QCTO PM PowerPoint Presentations — one .pptx deck per real PM module,
bundled into a single ZIP file, mirroring the KM PowerPoint builder's structure, design,
and content-generation approach. Each real performance_assessment item (PM's atomic
content unit — a specific practical task) is fed into generate_slide_content (the same AI
function the non-QCTO presentation builder uses) alongside the module's real assessment
criteria, producing genuine teach/practice slide pairs — not the raw task text and
criteria reprinted as slide title/bullets. Uses the same house presentation style as KM's
deck: split top bar, corner flag, footer band with organization name and page numbers."""
from io import BytesIO
import zipfile
from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN
from app.services.ai_service import generate_slide_content, parallel_map
from app.services.document_service import DEFAULT_PRIMARY, DEFAULT_SECONDARY

DEFAULT_ACCENT = "F39C12"


def _pptx_rgb(hex_str, fallback):
    try:
        return RGBColor.from_string((hex_str or fallback).lstrip("#").upper())
    except (ValueError, TypeError):
        return RGBColor.from_string(fallback)


def _add_footer_lines(slide, prs, module_line, contact_line, page_number, primary):
    """Clean, text-only footer — module code/title on one small line, organization
    contact details on a second line beneath it, page number at the right. No background
    band or decorative bar."""
    footer_top = prs.slide_height - Inches(0.55)
    box = slide.shapes.add_textbox(Inches(0.5), footer_top, prs.slide_width - Inches(1.8), Inches(0.45))
    tf = box.text_frame
    tf.margin_top = Emu(0)
    tf.margin_bottom = Emu(0)
    tf.word_wrap = True
    p1 = tf.paragraphs[0]
    p1.text = module_line
    p1.runs[0].font.size = Pt(9)
    p1.runs[0].font.color.rgb = primary
    if contact_line:
        p2 = tf.add_paragraph()
        p2.text = contact_line
        p2.runs[0].font.size = Pt(7)
        p2.runs[0].font.color.rgb = RGBColor(0x80, 0x80, 0x80)

    page_box = slide.shapes.add_textbox(prs.slide_width - Inches(1.2), footer_top, Inches(0.9), Inches(0.3))
    p_tf = page_box.text_frame
    p_tf.margin_top = Emu(0)
    p = p_tf.paragraphs[0]
    p.alignment = PP_ALIGN.RIGHT
    p.text = str(page_number)
    p.runs[0].font.size = Pt(9)
    p.runs[0].font.color.rgb = primary


def _add_slide_border(slide, prs, primary, accent, inset_inches=0.12, inner_gap_inches=0.07,
                       outer_weight_pt=3.0, inner_weight_pt=1.25):
    """Two-line decorative frame -- a thicker accent-colored outer line and a thinner
    primary-colored inner line -- plus a small chevron accent in the top-right corner,
    so the deck reads as designed rather than a bare white background. Outline shapes
    only, no fill, so they never cover title/body/footer content."""
    outer = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE,
        Inches(inset_inches), Inches(inset_inches),
        prs.slide_width - Inches(inset_inches * 2),
        prs.slide_height - Inches(inset_inches * 2),
    )
    outer.fill.background()
    outer.line.color.rgb = accent
    outer.line.width = Pt(outer_weight_pt)
    outer.shadow.inherit = False

    inner_inset = inset_inches + inner_gap_inches
    inner = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE,
        Inches(inner_inset), Inches(inner_inset),
        prs.slide_width - Inches(inner_inset * 2),
        prs.slide_height - Inches(inner_inset * 2),
    )
    inner.fill.background()
    inner.line.color.rgb = primary
    inner.line.width = Pt(inner_weight_pt)
    inner.shadow.inherit = False

    arrow = slide.shapes.add_shape(
        MSO_SHAPE.CHEVRON,
        prs.slide_width - Inches(0.75), Inches(0.18),
        Inches(0.5), Inches(0.3),
    )
    arrow.fill.solid()
    arrow.fill.fore_color.rgb = accent
    arrow.line.fill.background()
    arrow.shadow.inherit = False

    return outer, inner, arrow


def _add_eyebrow(slide, prs, text, color):
    """Small, bold label above a slide's main title."""
    box = slide.shapes.add_textbox(Inches(0.5), Inches(0.35), prs.slide_width - Inches(1.0), Inches(0.4))
    tf = box.text_frame
    tf.margin_top = Emu(0)
    p = tf.paragraphs[0]
    p.text = text.upper()
    p.runs[0].font.size = Pt(12)
    p.runs[0].font.bold = True
    p.runs[0].font.color.rgb = color


def _compute_bullet_font_size(bullets):
    """Scales bullet font size down as content grows, so text stays within the slide
    body area rather than overflowing it."""
    total_chars = sum(len(b) for b in bullets)
    if total_chars > 700 or len(bullets) > 7:
        return 14
    if total_chars > 500 or len(bullets) > 6:
        return 16
    if total_chars > 350:
        return 18
    return 20


def _build_pm_module_deck(module, qualification_title, organization_name, brand_colors, logo_bytes=None,
                           accreditation_info=None, job_id=None):
    primary = _pptx_rgb(brand_colors.get("primary"), DEFAULT_PRIMARY)
    secondary = _pptx_rgb(brand_colors.get("secondary"), DEFAULT_SECONDARY)
    accent = _pptx_rgb(brand_colors.get("accent"), DEFAULT_ACCENT)
    accreditation_info = accreditation_info or {}

    module_line_parts = [module.get("module_code", ""), module.get("title", "")]
    module_line = " · ".join(p for p in module_line_parts if p)
    contact_bits = [b for b in [
        accreditation_info.get("organization_address"),
        accreditation_info.get("organization_phone"),
        accreditation_info.get("organization_email"),
        accreditation_info.get("organization_website"),
    ] if b]
    contact_line = "  ·  ".join(contact_bits)

    prs = Presentation()
    module_title = f"{module.get('module_code', '')}: {module.get('title', '')}"
    page_number = 1

    # --- Title slide ---
    title_slide_layout = prs.slide_layouts[0]
    slide = prs.slides.add_slide(title_slide_layout)
    _add_footer_lines(slide, prs, module_line, contact_line, page_number, primary)
    _add_slide_border(slide, prs, primary, accent)

    slide.shapes.title.text = module_title
    title_run = slide.shapes.title.text_frame.paragraphs[0].runs[0]
    title_run.font.color.rgb = primary
    title_run.font.bold = True
    title_run.font.size = Pt(36)

    if qualification_title:
        subtitle_placeholder = slide.placeholders[1]
        subtitle_placeholder.text = qualification_title
        subtitle_placeholder.text_frame.paragraphs[0].runs[0].font.color.rgb = secondary
        subtitle_placeholder.text_frame.paragraphs[0].runs[0].font.italic = True
        subtitle_placeholder.text_frame.paragraphs[0].runs[0].font.size = Pt(18)

    if logo_bytes:
        try:
            slide.shapes.add_picture(BytesIO(logo_bytes), Inches(0.4), Inches(0.4), height=Inches(0.9))
        except Exception:
            pass

    pa_items = module.get("performance_assessment", [])
    pa_texts = [pa.get("text", "") if isinstance(pa, dict) else (pa or "") for pa in pa_items]
    pa_codes = [pa.get("code", "") if isinstance(pa, dict) else "" for pa in pa_items]

    # --- Overview slide ---
    page_number += 1
    overview_slide = prs.slides.add_slide(prs.slide_layouts[1])
    _add_footer_lines(overview_slide, prs, module_line, contact_line, page_number, primary)
    _add_slide_border(overview_slide, prs, primary, accent)
    overview_title = overview_slide.shapes.title
    overview_title.left = Inches(0.5)
    overview_title.top = Inches(0.5)
    overview_title.width = prs.slide_width - Inches(1.0)
    overview_title.text = "What This Module Covers"
    overview_title.text_frame.paragraphs[0].runs[0].font.color.rgb = primary
    overview_title.text_frame.paragraphs[0].runs[0].font.bold = True

    overview_body = overview_slide.placeholders[1]
    overview_body.left = Inches(0.5)
    overview_body.top = Inches(1.6)
    overview_body.width = prs.slide_width - Inches(1.0)
    overview_body.height = prs.slide_height - Inches(2.2)
    overview_body.text_frame.clear()
    overview_body.text_frame.word_wrap = True
    overview_lines = [f"{code} {text}" if code else text for code, text in zip(pa_codes, pa_texts)]
    for i, line in enumerate(overview_lines):
        p = overview_body.text_frame.paragraphs[0] if i == 0 else overview_body.text_frame.add_paragraph()
        p.text = line
        p.font.size = Pt(16)

    # --- Content slides: real AI-generated teach/practice pairs per performance-assessment
    # item, with a section-divider slide introducing each item first ---
    module_criteria = module.get("assessment_criteria") or []
    bullet_layout = prs.slide_layouts[1]

    pa_results = parallel_map(
        pa_texts,
        lambda pa_text: generate_slide_content(pa_text, module_criteria, course_title=qualification_title, job_id=job_id),
        max_workers=3,
    )

    for item_index, (pa_code, pa_text, result) in enumerate(zip(pa_codes, pa_texts, pa_results), start=1):
        # Section divider slide
        page_number += 1
        divider = prs.slides.add_slide(prs.slide_layouts[6])
        _add_footer_lines(divider, prs, module_line, contact_line, page_number, primary)
        _add_slide_border(divider, prs, primary, accent)
        divider_box = divider.shapes.add_textbox(Inches(0.8), Inches(2.6), prs.slide_width - Inches(1.6), Inches(2.0))
        d_tf = divider_box.text_frame
        d_tf.word_wrap = True
        d_p1 = d_tf.paragraphs[0]
        d_p1.text = f"PRACTICAL SKILL {item_index}" + (f"  ·  {pa_code}" if pa_code else "")
        d_p1.runs[0].font.size = Pt(16)
        d_p1.runs[0].font.bold = True
        d_p1.runs[0].font.color.rgb = secondary
        d_p2 = d_tf.add_paragraph()
        d_p2.text = pa_text
        d_p2.runs[0].font.size = Pt(26)
        d_p2.runs[0].font.bold = True
        d_p2.runs[0].font.color.rgb = primary

        if result is None:
            continue

        for slide_data in result.get("slides", []):
            page_number += 1
            slide_title = slide_data.get("title", pa_text)
            bullets = slide_data.get("bullets", [])
            speaker_notes = slide_data.get("speaker_notes", "")
            image_search_term = slide_data.get("image_search_term")

            photo_bytes = None
            diagram_bytes = None
            if slide_data.get("model_diagram"):
                from app.services.model_diagram_service import slide_model_diagram_png
                diagram_bytes = slide_model_diagram_png(slide_data.get("model_diagram"), str(primary), str(accent), deck=prs)
            if image_search_term and not diagram_bytes:
                from app.services.image_service import fetch_stock_photo
                photo_bytes = fetch_stock_photo(image_search_term)

            slide = prs.slides.add_slide(bullet_layout)
            _add_footer_lines(slide, prs, module_line, contact_line, page_number, primary)
            _add_slide_border(slide, prs, primary, accent)
            _add_eyebrow(slide, prs, (f"{pa_code}  " if pa_code else "") + pa_text, secondary)

            title_shape = slide.shapes.title
            title_shape.left = Inches(0.5)
            title_shape.top = Inches(0.85)
            title_shape.width = prs.slide_width - Inches(1.0)
            title_shape.height = Inches(1.0)
            title_shape.text = slide_title
            title_shape.text_frame.word_wrap = True
            title_shape.text_frame.paragraphs[0].runs[0].font.color.rgb = primary
            title_shape.text_frame.paragraphs[0].runs[0].font.bold = True

            content_width = prs.slide_width - Inches(1.0)
            if diagram_bytes:
                body_width = int(content_width * 0.50)
            else:
                body_width = int(content_width * 0.55) if photo_bytes else content_width

            body = slide.placeholders[1]
            body.left = Inches(0.5)
            body.top = Inches(2.0)
            body.width = body_width
            body.height = prs.slide_height - Inches(2.5)
            body.text_frame.clear()
            body.text_frame.word_wrap = True
            bullet_font_size = _compute_bullet_font_size(bullets)
            for i, bullet in enumerate(bullets):
                p = body.text_frame.paragraphs[0] if i == 0 else body.text_frame.add_paragraph()
                p.text = bullet
                p.font.size = Pt(bullet_font_size)

            if diagram_bytes:
                from app.services.model_diagram_service import add_fitted_picture
                add_fitted_picture(slide, diagram_bytes, Inches(0.5) + body_width + Inches(0.3), Inches(2.0),
                                   content_width - body_width - Inches(0.3), prs.slide_height - Inches(2.5))
            if photo_bytes:
                image_left = Inches(0.5) + body_width + Inches(0.3)
                image_width = content_width - body_width - Inches(0.3)
                from app.services.model_diagram_service import add_cover_picture
                add_cover_picture(slide, photo_bytes, image_left, Inches(2.0),
                                  image_width, prs.slide_height - Inches(2.5))

            if speaker_notes:
                slide.notes_slide.notes_text_frame.text = speaker_notes

    buf = BytesIO()
    prs.save(buf)
    buf.seek(0)
    return buf


def build_qcto_pm_powerpoint_zip(title: str, syllabus_content: dict, organization_name: str = None,
                                  logo_bytes: bytes = None, brand_colors: dict = None,
                                  accreditation_info: dict = None, job_id: str = None) -> BytesIO:
    brand_colors = brand_colors or {}
    accreditation_info = accreditation_info or {}
    qualification_title = syllabus_content.get("qualification_title", "") or title

    pm_modules = [m for m in syllabus_content.get("modules", []) if m.get("module_type") == "PM"]

    zip_buf = BytesIO()
    with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for module in pm_modules:
            deck_buf = _build_pm_module_deck(module, qualification_title, organization_name, brand_colors, logo_bytes, accreditation_info=accreditation_info, job_id=job_id)
            safe_title = "".join(c if c.isalnum() or c in " _-" else "" for c in module.get("title", "Module")).strip().replace(" ", "_")
            filename = f"{module.get('module_code', 'Module')}_{safe_title}.pptx"
            zf.writestr(filename, deck_buf.getvalue())

    zip_buf.seek(0)
    return zip_buf


def build_qcto_pm_powerpoint_zip_adapter(title, units, organization_name=None, seta=None,
                                           nqf_level=None, logo_bytes=None, brand_colors=None,
                                           accreditation_info=None, job_id=None, **kwargs):
    """Adapter matching the standard DOCUMENT_BUILDERS call signature."""
    syllabus_content = {"modules": units} if isinstance(units, list) else (units or {"modules": []})
    return build_qcto_pm_powerpoint_zip(
        title=title,
        syllabus_content=syllabus_content,
        organization_name=organization_name,
        logo_bytes=logo_bytes,
        brand_colors=brand_colors,
        accreditation_info=accreditation_info,
        job_id=job_id,
    )
