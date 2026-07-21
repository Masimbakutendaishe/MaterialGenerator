# Organization model (tenant, branding)
"""Organization model — the tenant. Every other resource is scoped to one of these."""
import uuid
from datetime import datetime, timezone
from app.extensions import db


class Organization(db.Model):
    __tablename__ = "organizations"

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = db.Column(db.String(255), nullable=False)
    logo_url = db.Column(db.String(500), nullable=True)
    brand_colors = db.Column(db.JSON, nullable=True)  # e.g. {"primary": "#123456", "secondary": "#abcdef"}
    plan = db.Column(db.String(50), nullable=False, default="pay_per_use")  # "subscription" | "pay_per_use"
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    users = db.relationship("User", back_populates="organization", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Organization {self.name}>"