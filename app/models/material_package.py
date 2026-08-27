"""MaterialPackage — groups multiple GenerationJob documents into one requested set
(e.g. Masterclass = textbook + presentation + assessment)."""
import uuid
from datetime import datetime, timezone
from app.extensions import db

PACKAGE_TYPES = ("masterclass", "full_training_set", "qcto_full_set", "qcto_part_qualification", "qcto_skills_programme")

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
    # Full Qualification: KM + PM + WM + Assessments + Video Guide. This is the real,
    # complete Full Qualification document list for what's currently buildable — the fuller
    # 21-document breakdown (Facilitator/Assessment Guides, POE, Learner Workbook, ISA,
    # Final Exam, per-module PowerPoint, WM Guide for Industry Supervisors, etc.) still needs
    # builders written; add each here as it's built.
    "qcto_full_set": [
        "qcto_knowledge_modules",
        "qcto_km_facilitator_guide",
        "qcto_km_assessment_guide",
        "qcto_km_poe",
        "qcto_km_learner_workbook",
        "qcto_km_powerpoint",
        "qcto_practical_modules",
        "qcto_pm_facilitator_guide",
        "qcto_pm_assessment_guide",
        "qcto_pm_powerpoint",
        "qcto_pm_poe",
        "qcto_workplace_modules",
        "qcto_wm_supervisor_guide",
        "qcto_workplace_logbook",
        "qcto_video_guide",
        "qcto_km_assessment",
        "qcto_pm_assessment",
        "qcto_isa",
        "qcto_final_exam",
        "qcto_learning_matrix",
    ],
    # Part Qualification:
    # Part Qualification: same document set as Full Qualification, plus a Learning Matrix
    # (not yet built — this list is identical to qcto_full_set as an interim placeholder
    # until the Learning Matrix builder exists; add "programme_alignment_matrix" or a
    # dedicated learning-matrix subtype here once it's wired up for QCTO content).
    "qcto_part_qualification": [
        "qcto_knowledge_modules",
        "qcto_practical_modules",
        "qcto_workplace_modules",
        "qcto_workplace_logbook",
        "qcto_video_guide",
        "qcto_km_assessment",
        "qcto_pm_assessment",
        "qcto_isa",
    ],
    # Skills Programme:
    # Skills Programme: same KM + PM documents as Full Qualification, but should replace
    # ISA + Final Exam with a single FISA (Final Integrated Summative Assessment) — neither
    # ISA nor FISA exist as builders yet, so this is an interim placeholder identical to
    # qcto_full_set; revisit once FISA is built.
    "qcto_skills_programme": [
        "qcto_knowledge_modules",
        "qcto_practical_modules",
        "qcto_workplace_modules",
        "qcto_workplace_logbook",
        "qcto_video_guide",
        "qcto_km_assessment",
        "qcto_pm_assessment",
        "qcto_fisa",
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