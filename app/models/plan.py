"""Plan model — defines a subscription tier's limits. Organizations are optionally
assigned a plan; enforcement (blocking generation once a limit is hit) is built
separately once you're ready to actually turn this on."""
import uuid
from datetime import datetime, timezone
from app.extensions import db


class Plan(db.Model):
    __tablename__ = "plans"

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = db.Column(db.String(100), nullable=False)  # e.g. "Starter", "Growth", "Institution"
    monthly_package_limit = db.Column(db.Integer, nullable=True)  # None = unlimited
    monthly_document_limit = db.Column(db.Integer, nullable=True)  # None = unlimited
    price_zar = db.Column(db.Integer, nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)  # lets you retire old plans without deleting history
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    organizations = db.relationship("Organization", back_populates="plan_tier")

    def __repr__(self):
        return f"<Plan {self.name}>"