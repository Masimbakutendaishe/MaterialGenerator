"""Dedicated builder for the Summative Assessment — case-study driven, with a formal
Formative/Summative score cover page, matching real accredited exam format."""
from io import BytesIO
from docx import Document
from docx.shared import Pt, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH
from app.services.ai_service import generate_summative_assessment_content
from app.services.document_service import _hex_to_rgb, _add_branded_header_footer, DEFAULT_PRIMARY


def build_summative_assessment_docx(title: str, units: list, organization_name: str = None,
                                     seta: str = None, nqf_level: str = None, logo_bytes: bytes = None,
                                     brand_colors: dict = None, job_id: str = None) -> BytesIO:
    brand_colors = brand_colors or {}
    primary_hex = brand_colors.get("primary", DEFAULT_PRIMARY).lstrip("#") if brand_colors.get("primary") else DEFAULT_PRIMARY
    primary = _hex_to_rgb(primary_hex, DEFAULT_PRIMARY)

    content = generate_summative_assessment_content(title, units, seta=seta, nqf_level=nqf_level, job_id=job_id)

    doc = Document()

    from app.services.document_service import _build_branded_cover
    _build_branded_cover(doc, title, "Summative Assessment", organization_name, logo_bytes, primary, primary_hex, primary)

    # Score cover table

    # Score cover table
    section_a_marks = sum(q.get("marks", 1) for q in content.get("section_a", []))
    section_b_marks = sum(q.get("marks", 0) for q in content.get("section_b", []))
    section_c_marks = sum(q.get("marks", 0) for q in content.get("section_c", []))
    total_marks = section_a_marks + section_b_marks + section_c_marks

    table = doc.add_table(rows=2, cols=4)
    table.style = "Table Grid"
    headers = ["Assessment Type", "Learner's Score", "Maximum Score", "Competent / Not Yet Competent"]
    for i, h in enumerate(headers):
        cell = table.cell(0, i)
        cell.text = h
        cell.paragraphs[0].runs[0].bold = True
        cell.paragraphs[0].runs[0].font.size = Pt(10)
    table.cell(1, 0).text = "Summative"
    table.cell(1, 2).text = str(total_marks)

    doc.add_paragraph()
    sig = doc.add_paragraph()
    sig.add_run("Assessor signature: " + "_" * 25 + "     Moderator signature: " + "_" * 25)
    sig.runs[0].font.size = Pt(10)

    doc.add_page_break()

    # Case study
    cs_heading = doc.add_paragraph()
    cs_run = cs_heading.add_run("Case Study")
    cs_run.bold = True
    cs_run.font.size = Pt(14)
    cs_run.font.color.rgb = primary

    cs_text = doc.add_paragraph()
    cs_text.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    cs_italic = cs_text.add_run(content.get("case_study", ""))
    cs_italic.italic = True

    doc.add_page_break()

    # Section A
    _render_section(doc, "SECTION A", "Multiple Choice — refer to the case study", content.get("section_a", []), primary, section_a_marks, mc=True)
    doc.add_page_break()

    # Section B
    _render_section(doc, "SECTION B", "Short Knowledge Questions", content.get("section_b", []), primary, section_b_marks, mc=False)
    doc.add_page_break()

    # Section C
    _render_section(doc, "SECTION C", "Long Question", content.get("section_c", []), primary, section_c_marks, mc=False)

    doc.add_page_break()
    from app.services.document_service import _add_signature_block
    _add_signature_block(doc)
    _add_branded_header_footer(doc, logo_bytes=logo_bytes, qualification_name=title, organization_name=organization_name, primary_hex=primary_hex)

    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    return buffer


def _render_section(doc, section_label, section_desc, questions, primary, total_marks, mc=False):
    heading = doc.add_paragraph()
    h_run = heading.add_run(f"{section_label}  ({total_marks})")
    h_run.bold = True
    h_run.font.size = Pt(14)
    h_run.font.color.rgb = primary

    desc = doc.add_paragraph()
    desc.add_run(section_desc).italic = True

    for i, q in enumerate(questions, start=1):
        q_para = doc.add_paragraph()
        q_para.paragraph_format.space_before = Pt(10)
        q_run = q_para.add_run(f"{i}. {q.get('question_text', '')}")
        marks_run = q_para.add_run(f"  ({q.get('marks', 0)})")
        marks_run.italic = True
        marks_run.font.size = Pt(9)

        if mc and q.get("options"):
            import re
            for j, option in enumerate(q["options"]):
                letter = chr(65 + j)
                # Strip any letter prefix the AI may have already included (e.g. "A. ", "A) ", "A: ")
                cleaned_option = re.sub(r'^[A-Da-d][\.\)\:]\s*', '', str(option)).strip()
                opt_para = doc.add_paragraph()
                opt_para.paragraph_format.left_indent = Inches(0.4)
                opt_para.paragraph_format.space_after = Pt(2)
                opt_para.add_run(f"{letter}. {cleaned_option}")
        else:
            blank_lines = min(q.get("blank_lines", 3), 8)  # cap so essay answers don't sprawl across pages
            for _ in range(blank_lines):
                line_para = doc.add_paragraph()
                line_para.paragraph_format.space_before = Pt(0)
                line_para.paragraph_format.space_after = Pt(14)  # more breathing room between ruled lines
                line_para.add_run("_" * 100)
