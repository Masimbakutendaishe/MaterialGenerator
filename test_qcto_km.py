from app import create_app
app = create_app()
with app.app_context():
    from app.services.qcto_knowledge_module_service import build_qcto_knowledge_module_docx

    fake_syllabus_content = {
        "modules": [
            {
                "module_type": "KM",
                "module_code": "718302-000-00-KM-01",
                "title": "Personal Mastery and Inter-personal Relationships",
                "nqf_level": "3",
                "credits": 4,
                "topics": [
                    {"topic_code": "KM-01-KT01", "title": "Personal Mastery", "weight": "30%"},
                    {"topic_code": "KM-01-KT02", "title": "Planning and Problem-solving", "weight": "30%"},
                ],
            }
        ]
    }

    buf = build_qcto_knowledge_module_docx(
        title="Food and Beverage Packaging Operator",
        syllabus_content=fake_syllabus_content,
        organization_name="Test Training Academy",
        brand_colors={"primary": "1A5276", "secondary": "2874A6", "accent": "F39C12"},
    )
    with open("test_qcto_km.docx", "wb") as f:
        f.write(buf.getvalue())
    print("saved")