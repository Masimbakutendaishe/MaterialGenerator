"""Builds the QCTO KM PowerPoint Presentations — one .pptx deck per real KM module,
bundled into a single ZIP file. Reuses generate_slide_content (the same AI function the
non-QCTO presentation builder uses) to write genuine teach/practice slide pairs per topic —
grounded in the topic's real title and assessment criteria, but actually written as
punchy, pedagogically-designed teaching content, not the raw criteria text reprinted as
bullets. Also reuses the app's established presentation house style from
presentation_service.py (split top bar, corner flag, footer band with organization name)
and adds page numbers to the footer."""
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
    band or decorative bar, matching the reference material's actual look — a solid
    full-width footer band reads as generic template filler."""
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
def _add_eyebrow(slide, prs, text, color):
    """Small, bold label above a slide's main title — e.g. the topic code and topic
    name, giving orientation without a decorative bar or stripe."""
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
    body area rather than overflowing it — thresholds tuned against realistic bullet
    lengths at a 9-inch usable body width."""
    total_chars = sum(len(b) for b in bullets)
    if total_chars > 700 or len(bullets) > 7:
        return 14
    if total_chars > 500 or len(bullets) > 6:
        return 16
    if total_chars > 350:
        return 18
    return 20


def _build_km_module_deck(module, qualification_title, organization_name, brand_colors, logo_bytes=None,
                           accreditation_info=None, job_id=None):
    primary = _pptx_rgb(brand_colors.get("primary"), DEFAULT_PRIMARY)
    secondary = _pptx_rgb(brand_colors.get("secondary"), DEFAULT_SECONDARY)
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
            pass  # unsupported image format for python-pptx (e.g. SVG) — skip rather than fail the deck

    # --- Overview slide ---
    page_number += 1
    topics = module.get("topics", [])
    overview_slide = prs.slides.add_slide(prs.slide_layouts[1])
    _add_footer_lines(overview_slide, prs, module_line, contact_line, page_number, primary)
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
    overview_lines = [f"{t.get('topic_code', '')} {t.get('title', '')}" for t in topics]
    for i, line in enumerate(overview_lines):
        p = overview_body.text_frame.paragraphs[0] if i == 0 else overview_body.text_frame.add_paragraph()
        p.text = line
        p.font.size = Pt(18)

    # --- Content slides: real AI-generated teach/practice pairs per topic, with a
    # section-divider slide introducing each topic first ---
    bullet_layout = prs.slide_layouts[1]

    topic_results = parallel_map(
        topics,
        lambda t: generate_slide_content(t.get("title", ""), t.get("assessment_criteria") or [], course_title=qualification_title, job_id=job_id),
        max_workers=3,
    )

    for topic_index, (topic, result) in enumerate(zip(topics, topic_results), start=1):
        unit_name = topic.get("title", "")
        topic_code = topic.get("topic_code", "")

        # Section divider slide
        page_number += 1
        divider = prs.slides.add_slide(prs.slide_layouts[6])
        _add_footer_lines(divider, prs, module_line, contact_line, page_number, primary)
        divider_box = divider.shapes.add_textbox(Inches(0.8), Inches(2.6), prs.slide_width - Inches(1.6), Inches(2.0))
        d_tf = divider_box.text_frame
        d_tf.word_wrap = True
        d_p1 = d_tf.paragraphs[0]
        d_p1.text = f"KNOWLEDGE TOPIC {topic_index}"
        d_p1.runs[0].font.size = Pt(16)
        d_p1.runs[0].font.bold = True
        d_p1.runs[0].font.color.rgb = secondary
        d_p2 = d_tf.add_paragraph()
        d_p2.text = unit_name
        d_p2.runs[0].font.size = Pt(30)
        d_p2.runs[0].font.bold = True
        d_p2.runs[0].font.color.rgb = primary

        if result is None:
            continue

        for slide_data in result.get("slides", []):
            page_number += 1
            slide_title = slide_data.get("title", unit_name)
            bullets = slide_data.get("bullets", [])
            speaker_notes = slide_data.get("speaker_notes", "")
            image_search_term = slide_data.get("image_search_term")

            photo_bytes = None
            if image_search_term:
                from app.services.image_service import fetch_stock_photo
                photo_bytes = fetch_stock_photo(image_search_term)

            slide = prs.slides.add_slide(bullet_layout)
            _add_footer_lines(slide, prs, module_line, contact_line, page_number, primary)
            _add_eyebrow(slide, prs, f"{topic_code}  {unit_name}", secondary)

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

            if photo_bytes:
                image_left = Inches(0.5) + body_width + Inches(0.3)
                image_width = content_width - body_width - Inches(0.3)
                slide.shapes.add_picture(
                    BytesIO(photo_bytes), image_left, Inches(2.0),
                    width=image_width, height=prs.slide_height - Inches(2.5),
                )

            if speaker_notes:
                slide.notes_slide.notes_text_frame.text = speaker_notes

    buf = BytesIO()
    prs.save(buf)
    buf.seek(0)
    return buf

def build_qcto_km_powerpoint_zip(title: str, syllabus_content: dict, organization_name: str = None,
                                  logo_bytes: bytes = None, brand_colors: dict = None,
                                  accreditation_info: dict = None, job_id: str = None) -> BytesIO:
    brand_colors = brand_colors or {}
    accreditation_info = accreditation_info or {}
    qualification_title = syllabus_content.get("qualification_title", "") or title

    km_modules = [m for m in syllabus_content.get("modules", []) if m.get("module_type") == "KM"]

    zip_buf = BytesIO()
    with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for module in km_modules:
            deck_buf = _build_km_module_deck(module, qualification_title, organization_name, brand_colors, logo_bytes, accreditation_info=accreditation_info, job_id=job_id)
            safe_title = "".join(c if c.isalnum() or c in " _-" else "" for c in module.get("title", "Module")).strip().replace(" ", "_")
            filename = f"{module.get('module_code', 'Module')}_{safe_title}.pptx"
            zf.writestr(filename, deck_buf.getvalue())

    zip_buf.seek(0)
    return zip_buf


def build_qcto_km_powerpoint_zip_adapter(title, units, organization_name=None, seta=None,
                                           nqf_level=None, logo_bytes=None, brand_colors=None,
                                           accreditation_info=None, job_id=None, **kwargs):
    """Adapter matching the standard DOCUMENT_BUILDERS call signature."""
    syllabus_content = {"modules": units} if isinstance(units, list) else (units or {"modules": []})
    return build_qcto_km_powerpoint_zip(
        title=title,
        syllabus_content=syllabus_content,
        organization_name=organization_name,
        logo_bytes=logo_bytes,
        brand_colors=brand_colors,
        accreditation_info=accreditation_info,
        job_id=job_id,
    )
