# GenerationJob model (async status tracking)
"""GenerationJob model — tracks the async status of a material generation request."""
import uuid
from datetime import datetime, timezone
from app.extensions import db


class GenerationJob(db.Model):
    __tablename__ = "generation_jobs"

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = db.Column(db.String(36), db.ForeignKey("organizations.id"), nullable=False)
    syllabus_id = db.Column(db.String(36), db.ForeignKey("syllabi.id"), nullable=False)

    material_type = db.Column(db.String(50), nullable=False)  # "textbook" | "presentation"
    status = db.Column(db.String(50), nullable=False, default="queued")  # "queued" | "running" | "done" | "failed"
    result_file_path = db.Column(db.String(500), nullable=True)  # local path for now, S3 URL later

    
    error_message = db.Column(db.Text, nullable=True)
    

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    task_id = db.Column(db.String(255), nullable=True)  # Celery task ID, needed to revoke/cancel
    triggered_by_user_id = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=True)
    package_id = db.Column(db.String(36), db.ForeignKey("material_packages.id"), nullable=True)
    document_subtype = db.Column(db.String(50), nullable=True)  # e.g. "assessment", "facilitator_guide" — NULL for legacy single-document jobs

    def __repr__(self):
        return f"<GenerationJob {self.id} {self.material_type} {self.status}>"