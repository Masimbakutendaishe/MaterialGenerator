"""Builds a .pptx presentation from structured syllabus content, styled with organization branding."""
from io import BytesIO
from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from app.services.ai_service import generate_slide_content

DEFAULT_PRIMARY = "1A5276"
DEFAULT_SECONDARY = "2874A6"
DEFAULT_ACCENT = "F39C12"


def _hex_to_rgb(hex_str: str, fallback: str) -> RGBColor:
    try:
        return RGBColor.from_string((hex_str or fallback).lstrip("#").upper())
    except (ValueError, TypeError):
        return RGBColor.from_string(fallback)


def _add_split_top_bar(slide, prs, color_left: RGBColor, color_right: RGBColor):
    """Two-tone top bar: left two-thirds in primary, right third in secondary — a layered
    look without relying on python-pptx's less reliable native gradient fills."""
    bar_height = Emu(137160)  # ~0.15 inch
    split_point = int(prs.slide_width * 0.65)

    left_bar = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Emu(0), Emu(0), split_point, bar_height)
    left_bar.fill.solid()
    left_bar.fill.fore_color.rgb = color_left
    left_bar.line.fill.background()

    right_bar = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, split_point, Emu(0), prs.slide_width - split_point, bar_height)
    right_bar.fill.solid()
    right_bar.fill.fore_color.rgb = color_right
    right_bar.line.fill.background()


def _add_corner_flag(slide, accent: RGBColor):
    """Small flag-shaped accent in the top-left for a distinctive brand mark."""
    flag = slide.shapes.add_shape(MSO_SHAPE.PENTAGON, Emu(0), Emu(137160), Inches(1.4), Inches(0.35))
    flag.fill.solid()
    flag.fill.fore_color.rgb = accent
    flag.line.fill.background()
    flag.rotation = 180


def _add_footer_band(slide, prs, organization_name: str, primary: RGBColor):
    """Solid corporate footer band across the bottom with the org name."""
    footer_height = Emu(320040)  # ~0.35 inch
    footer_top = prs.slide_height - footer_height
    footer = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Emu(0), footer_top, prs.slide_width, footer_height)
    footer.fill.solid()
    footer.fill.fore_color.rgb = primary
    footer.line.fill.background()

    if organization_name:
        tf = footer.text_frame
        tf.margin_left = Inches(0.3)
        tf.margin_top = Emu(0)
        tf.margin_bottom = Emu(0)
        tf.paragraphs[0].text = organization_name
        run = tf.paragraphs[0].runs[0]
        run.font.size = Pt(10)
        run.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)


def build_presentation_pptx(title: str, units: list, organization_name: str = None,
                             brand_colors: dict = None, seta: str = None, nqf_level: str = None,
                             logo_bytes: bytes = None) -> BytesIO:
    brand_colors = brand_colors or {}
    primary = _hex_to_rgb(brand_colors.get("primary"), DEFAULT_PRIMARY)
    secondary = _hex_to_rgb(brand_colors.get("secondary"), DEFAULT_SECONDARY)
    accent = _hex_to_rgb(brand_colors.get("accent"), DEFAULT_ACCENT)

    prs = Presentation()

    title_slide_layout = prs.slide_layouts[0]
    slide = prs.slides.add_slide(title_slide_layout)

    _add_split_top_bar(slide, prs, primary, secondary)
    _add_corner_flag(slide, accent)
    _add_footer_band(slide, prs, organization_name, primary)

    slide.shapes.title.text = title
    title_run = slide.shapes.title.text_frame.paragraphs[0].runs[0]
    title_run.font.color.rgb = primary
    title_run.font.bold = True
    title_run.font.size = Pt(40)

    if organization_name:
        subtitle_placeholder = slide.placeholders[1]
        subtitle_placeholder.text = organization_name
        subtitle_placeholder.text_frame.paragraphs[0].runs[0].font.color.rgb = secondary
        subtitle_placeholder.text_frame.paragraphs[0].runs[0].font.italic = True
        subtitle_placeholder.text_frame.paragraphs[0].runs[0].font.size = Pt(20)

    if logo_bytes:
        slide.shapes.add_picture(BytesIO(logo_bytes), Inches(0.4), Inches(0.55), height=Inches(0.9))

    bullet_layout = prs.slide_layouts[1]
    for unit in units:
        unit_name = unit.get("name", "Unit")
        outcomes = unit.get("outcomes", [])

        slide_content = generate_slide_content(unit_name, outcomes, seta=seta, nqf_level=nqf_level)
        bullets = slide_content.get("bullets", outcomes)

        slide = prs.slides.add_slide(bullet_layout)
        _add_split_top_bar(slide, prs, primary, secondary)
        _add_corner_flag(slide, accent)
        _add_footer_band(slide, prs, organization_name, primary)

        slide.shapes.title.text = unit_name
        title_run = slide.shapes.title.text_frame.paragraphs[0].runs[0]
        title_run.font.color.rgb = primary
        title_run.font.bold = True

        body = slide.placeholders[1].text_frame
        body.clear()
        if bullets:
            body.text = bullets[0]
            body.paragraphs[0].font.color.rgb = secondary
            body.paragraphs[0].font.size = Pt(20)
            for bullet in bullets[1:]:
                p = body.add_paragraph()
                p.text = bullet
                p.font.color.rgb = secondary
                p.font.size = Pt(20)

        speaker_notes = slide_content.get("speaker_notes", "")
        if speaker_notes:
            slide.notes_slide.notes_text_frame.text = speaker_notes

        if logo_bytes:
            slide.shapes.add_picture(BytesIO(logo_bytes), Inches(8.6), Inches(6.55), height=Inches(0.45))

    buffer = BytesIO()
    prs.save(buffer)
    buffer.seek(0)
    return buffer