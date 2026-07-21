"""Builds a .pptx presentation from structured syllabus content."""
from io import BytesIO
from pptx import Presentation
from pptx.util import Inches
from pptx.dml.color import RGBColor
from app.services.ai_service import generate_slide_content


def build_presentation_pptx(title: str, units: list, organization_name: str = None,
                             brand_colors: dict = None, seta: str = None, nqf_level: str = None,
                             logo_bytes: bytes = None) -> BytesIO:
    prs = Presentation()

    primary_color = None
    if brand_colors and brand_colors.get("primary"):
        try:
            hex_color = brand_colors["primary"].lstrip("#")
            primary_color = RGBColor.from_string(hex_color)
        except (ValueError, KeyError):
            primary_color = None

    title_slide_layout = prs.slide_layouts[0]
    slide = prs.slides.add_slide(title_slide_layout)
    slide.shapes.title.text = title
    if organization_name:
        slide.placeholders[1].text = organization_name
    if primary_color:
        slide.shapes.title.text_frame.paragraphs[0].runs[0].font.color.rgb = primary_color

    if logo_bytes:
        slide.shapes.add_picture(BytesIO(logo_bytes), Inches(8.2), Inches(0.3), height=Inches(1.0))

    bullet_layout = prs.slide_layouts[1]
    for unit in units:
        unit_name = unit.get("name", "Unit")
        outcomes = unit.get("outcomes", [])

        slide_content = generate_slide_content(unit_name, outcomes, seta=seta, nqf_level=nqf_level)
        bullets = slide_content.get("bullets", outcomes)

        slide = prs.slides.add_slide(bullet_layout)
        slide.shapes.title.text = unit_name

        body = slide.placeholders[1].text_frame
        body.clear()
        if bullets:
            body.text = bullets[0]
            for bullet in bullets[1:]:
                p = body.add_paragraph()
                p.text = bullet

        speaker_notes = slide_content.get("speaker_notes", "")
        if speaker_notes:
            slide.notes_slide.notes_text_frame.text = speaker_notes

        if primary_color:
            slide.shapes.title.text_frame.paragraphs[0].runs[0].font.color.rgb = primary_color

    buffer = BytesIO()
    prs.save(buffer)
    buffer.seek(0)
    return buffer