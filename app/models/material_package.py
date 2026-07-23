"""MaterialPackage — groups multiple GenerationJob documents into one requested set
(e.g. Masterclass = textbook + presentation + assessment)."""
import uuid
from datetime import datetime, timezone
from app.extensions import db

PACKAGE_TYPES = ("masterclass", "full_training_set")

# Document subtypes per package type — used by the trigger route to know what to generate
PACKAGE_DOCUMENTS = {
    "masterclass": ["textbook", "presentation", "assessment"],
    "full_training_set": [
        "presentation",
        "learner_manual",
        "facilitator_guide",
        "learner_induction_guide",
        "programme_strategy",
        "formative_assessment",
        "summative_assessment",
        "assessment_guide",
        "programme_alignment_matrix",
        "poe_guide",
        "moderator_guide",
    ],
}


class MaterialPackage(db.Model):
    __tablename__ = "material_packages"

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = db.Column(db.String(36), db.ForeignKey("organizations.id"), nullable=False)
    syllabus_id = db.Column(db.String(36), db.ForeignKey("syllabi.id"), nullable=False)
    triggered_by_user_id = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=True)
    package_type = db.Column(db.String(50), nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    jobs = db.relationship("GenerationJob", backref="package", order_by="GenerationJob.created_at")

    @property
    def status(self):
        """Computed from child jobs: done only if all done, partial_failure if mixed, else generating."""
        statuses = [j.status for j in self.jobs]
        if not statuses:
            return "generating"
        if all(s == "done" for s in statuses):
            return "done"
        if all(s in ("done", "failed", "cancelled") for s in statuses) and any(s != "done" for s in statuses):
            return "partial_failure"
        return "generating"

    def __repr__(self):
        return f"<MaterialPackage {self.id} {self.package_type}>"