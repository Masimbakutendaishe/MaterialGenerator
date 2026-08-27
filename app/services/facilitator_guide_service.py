"""Dedicated builder for the Facilitator/Assessor Guide — a model-answer key +
evaluation checklist + unit standard reference document, structurally distinct
from the other guide-style documents."""
from io import BytesIO
from docx import Document
from docx.shared import Pt, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH
from app.services.ai_service import generate_facilitator_guide_content
from app.services.document_service import _hex_to_rgb, _add_bottom_border, _add_branded_header_footer, DEFAULT_PRIMARY, DEFAULT_SECONDARY


def build_facilitator_guide_docx(title: str, units: list, organization_name: str = None,
                                  seta: str = None, nqf_level: str = None, logo_bytes: bytes = None,
                                  brand_colors: dict = None, job_id: str = None) -> BytesIO:
    brand_colors = brand_colors or {}
    primary_hex = brand_colors.get("primary", DEFAULT_PRIMARY).lstrip("#") if brand_colors.get("primary") else DEFAULT_PRIMARY
    primary = _hex_to_rgb(primary_hex, DEFAULT_PRIMARY)
    secondary = _hex_to_rgb(brand_colors.get("secondary", DEFAULT_SECONDARY).lstrip("#") if brand_colors.get("secondary") else DEFAULT_SECONDARY, DEFAULT_SECONDARY)

    doc = Document()

    from app.services.document_service import _build_branded_cover
    _build_branded_cover(doc, title, "Assessor Guide", organization_name, logo_bytes, primary, primary_hex, secondary)

    # --- Model Answers ---
    heading = doc.add_paragraph()
    hr = heading.add_run("Formative Assessment: Model Answers")
    hr.bold = True
    hr.font.size = Pt(18)
    hr.font.color.rgb = primary
    _add_bottom_border(heading, primary_hex)

    note = doc.add_paragraph()
    note_run = note.add_run(
        "Please note that the model answers in this document act as an example of what type "
        "of answers are expected from the learner. Assessors should use discretion and accept "
        "answers in the learner's own words that demonstrate the same understanding."
    )
    note_run.italic = True
    note_run.font.size = Pt(10)

    all_evaluation_items = []  # collected for the checklist table later

    for i, unit in enumerate(units, start=1):
        unit_name = unit.get("name", f"Unit {i}")
        outcomes = unit.get("outcomes", [])

        content = generate_facilitator_guide_content(unit_name, outcomes, course_title=title, seta=seta, nqf_level=nqf_level, job_id=job_id)

        section_heading = doc.add_paragraph()
        sh_run = section_heading.add_run(f"Section {i}: {unit_name}")
        sh_run.bold = True
        sh_run.font.size = Pt(14)
        sh_run.font.color.rgb = secondary

        activity_heading = doc.add_paragraph()
        activity_heading.add_run(content.get("activity_title", f"Activity {i}")).bold = True

        for q in content.get("questions", []):
            q_para = doc.add_paragraph()
            q_run = q_para.add_run(q.get("question_text", ""))
            marks_run = q_para.add_run(f"  ({q.get('marks', 0)})")
            marks_run.italic = True

            answer_para = doc.add_paragraph()
            answer_para.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
            points = q.get("model_answer_points", [])
            for point in points:
                run = answer_para.add_run(f"{point} ✓\n")
                run.italic = True
                run.font.color.rgb = secondary
                run.font.size = Pt(11)

            doc.add_paragraph()

        all_evaluation_items.append({"unit_name": unit_name, "criteria": content.get("evaluation_criteria", [])})
        doc.add_page_break()

    # --- Evaluation Checklist ---
    eval_heading = doc.add_paragraph()
    eh_run = eval_heading.add_run("Evaluation Checklist")
    eh_run.bold = True
    eh_run.font.size = Pt(18)
    eh_run.font.color.rgb = primary
    _add_bottom_border(eval_heading, primary_hex)

    for label in ["Learner Name:", "Assessor Name:", "Date:"]:
        p = doc.add_paragraph()
        p.add_run(f"{label} " + "_" * 40)

    doc.add_paragraph()

    table = doc.add_table(rows=1, cols=3)
    table.style = "Table Grid"
    hdr = table.rows[0].cells
    hdr[0].text = "Evaluation Criterion"
    hdr[1].text = "Met Requirements"
    hdr[2].text = "Did Not Meet Requirements"
    for cell in hdr:
        cell.paragraphs[0].runs[0].bold = True
        cell.paragraphs[0].runs[0].font.size = Pt(10)

    for item in all_evaluation_items:
        for criterion in item["criteria"]:
            row = table.add_row().cells
            row[0].text = criterion
            for cell in row:
                for p in cell.paragraphs:
                    for r in p.runs:
                        r.font.size = Pt(9)

    doc.add_paragraph()
    sig_p = doc.add_paragraph()
    sig_p.add_run("Assessor Signature: " + "_" * 30 + "     Date: " + "_" * 20)
    _add_branded_header_footer(doc, logo_bytes=logo_bytes, qualification_name=title, organization_name=organization_name, primary_hex=primary_hex)

    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    return buffer