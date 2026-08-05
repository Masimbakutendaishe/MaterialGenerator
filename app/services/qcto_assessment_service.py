"""Builds the QCTO Assessment document for KM or PM modules — cover page, then per-module
assessment sections with questions and blank ruled answer lines, matching the real
Ishida-style assessment format."""
from io import BytesIO
from docx import Document
from docx.shared import Pt, Inches
from app.services.ai_service import generate_qcto_assessment_content
from app.services.document_service import (
    _hex_to_rgb, _build_branded_cover, _add_page_numbers, _add_bottom_border,
    DEFAULT_PRIMARY, DEFAULT_SECONDARY,
)


def build_qcto_assessment_docx(title: str, syllabus_content: dict, module_type: str = "KM",
                                organization_name: str = None, logo_bytes: bytes = None,
                                brand_colors: dict = None, job_id: str = None) -> BytesIO:
    brand_colors = brand_colors or {}
    primary_hex = brand_colors.get("primary", DEFAULT_PRIMARY).lstrip("#") if brand_colors.get("primary") else DEFAULT_PRIMARY
    secondary_hex = brand_colors.get("secondary", DEFAULT_SECONDARY).lstrip("#") if brand_colors.get("secondary") else DEFAULT_SECONDARY
    primary = _hex_to_rgb(primary_hex, DEFAULT_PRIMARY)
    secondary = _hex_to_rgb(secondary_hex, DEFAULT_SECONDARY)

    label = "Knowledge Modules" if module_type == "KM" else "Practical Modules"

    doc = Document()
    _build_branded_cover(doc, title, f"Assessment Document — {label}", organization_name, logo_bytes, primary, primary_hex, secondary)

    for l in ["Learner Name:", "Facilitator Name:", "Date of Submission:"]:
        p = doc.add_paragraph()
        p.add_run(f"{l} " + "_" * 40)
        p.paragraph_format.space_after = Pt(14)
    doc.add_page_break()

    modules = [m for m in syllabus_content.get("modules", []) if m.get("module_type") == module_type]

    for m_index, module in enumerate(modules, start=1):
        module_heading = doc.add_paragraph()
        mh_run = module_heading.add_run(f"Module {m_index} Assessment")
        mh_run.bold = True
        mh_run.font.size = Pt(18)
        mh_run.font.color.rgb = primary
        _add_bottom_border(module_heading, primary_hex)

        subtitle_p = doc.add_paragraph()
        subtitle_p.add_run(module.get("title", "")).italic = True

        content = generate_qcto_assessment_content(module, job_id=job_id)

        q_number = 1
        for section in content.get("sections", []):
            section_heading = doc.add_paragraph()
            sh_run = section_heading.add_run(section.get("section_label", ""))
            sh_run.bold = True
            sh_run.font.size = Pt(13)
            sh_run.font.color.rgb = secondary
            section_heading.paragraph_format.space_before = Pt(14)

            for q in section.get("questions", []):
                q_para = doc.add_paragraph()
                q_para.paragraph_format.space_before = Pt(10)
                q_para.add_run(f"{q_number}. {q.get('question_text', '')}")
                q_number += 1

                blank_lines = min(q.get("blank_lines", 3), 6)
                for _ in range(blank_lines):
                    line_para = doc.add_paragraph()
                    line_para.paragraph_format.space_after = Pt(8)
                    line_para.add_run("_" * 100)

        doc.add_page_break()

    _add_page_numbers(doc)

    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    return buffer


def build_qcto_km_assessment_docx_adapter(title, units, organization_name=None, seta=None,
                                           nqf_level=None, logo_bytes=None, brand_colors=None,
                                           job_id=None, **kwargs):
    syllabus_content = {"modules": units} if isinstance(units, list) else (units or {"modules": []})
    return build_qcto_assessment_docx(
        title=title, syllabus_content=syllabus_content, module_type="KM",
        organization_name=organization_name, logo_bytes=logo_bytes,
        brand_colors=brand_colors, job_id=job_id,
    )


def build_qcto_pm_assessment_docx_adapter(title, units, organization_name=None, seta=None,
                                           nqf_level=None, logo_bytes=None, brand_colors=None,
                                           job_id=None, **kwargs):
    syllabus_content = {"modules": units} if isinstance(units, list) else (units or {"modules": []})
    return build_qcto_assessment_docx(
        title=title, syllabus_content=syllabus_content, module_type="PM",
        organization_name=organization_name, logo_bytes=logo_bytes,
        brand_colors=brand_colors, job_id=job_id,
    )