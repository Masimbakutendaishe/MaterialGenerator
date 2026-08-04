# Syllabus, SyllabusUnit models
"""Syllabus model — the source content that materials get generated from."""
import uuid
from datetime import datetime, timezone
from app.extensions import db


class Syllabus(db.Model):
    __tablename__ = "syllabi"

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = db.Column(db.String(36), db.ForeignKey("organizations.id"), nullable=False)
    created_by_user_id = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=False)

    title = db.Column(db.String(255), nullable=False)
    source = db.Column(db.String(50), nullable=False)  # "uploaded" | "typed" | "ai_generated"

    # Structured content: units, learning outcomes, assessment criteria — shape defined by syllabus_service
    content = db.Column(db.JSON, nullable=False, default=dict)

    # SETA/QCTO accreditation context, kept flexible since requirements vary by qualification
    accreditation_info = db.Column(db.JSON, nullable=True)  # e.g. {"seta": "MERSETA", "qualification_id": "..."}

    status = db.Column(db.String(50), nullable=False, default="draft")  # "draft" | "finalized"
    syllabus_type = db.Column(db.String(50), nullable=False, default="standard")  # "standard" | "qcto"
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    organization = db.relationship("Organization")
    created_by = db.relationship("User")

    def __repr__(self):
        return f"<Syllabus {self.title} ({self.source})>"