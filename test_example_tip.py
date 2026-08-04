from app import create_app
app = create_app()
with app.app_context():
    from app.services.document_service import _render_content_block, _add_page_numbers
    from docx import Document
    from docx.shared import RGBColor

    doc = Document()
    doc.add_heading("Example/Tip Block Test", level=1)

    _render_content_block(doc, {
        "type": "example_tip",
        "example": "At a packaging plant, an operator noticed repeated delays during daily startups. By arriving 10 minutes early to inspect the equipment, the operator ensured all systems were ready, reducing startup errors.",
        "tip": "Start your shift with a quick self-check: are you focused, calm, and prepared? A few minutes of preparation can prevent equipment errors and maintain product quality."
    }, "1A5276", RGBColor(0x28, 0x74, 0xA6))

    _add_page_numbers(doc)
    doc.save("test_example_tip.docx")
    print("saved")