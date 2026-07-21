"""User model — belongs to an Organization, or is a platform superadmin (organization_id=None)."""
import uuid
from datetime import datetime, timezone
from flask_login import UserMixin
from argon2 import PasswordHasher
from app.extensions import db

_ph = PasswordHasher()

# Valid roles: "superadmin" (platform, no org), "org_admin", "qa_reviewer", "user"
VALID_ROLES = ("superadmin", "org_admin", "qa_reviewer", "user")


class User(db.Model, UserMixin):
    __tablename__ = "users"

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = db.Column(db.String(36), db.ForeignKey("organizations.id"), nullable=True)
    email = db.Column(db.String(255), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(50), nullable=False, default="user")
    reports_to_user_id = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    organization = db.relationship("Organization", back_populates="users")
    reports_to = db.relationship("User", remote_side=[id], backref="direct_reports")

    def set_password(self, raw_password: str) -> None:
        self.password_hash = _ph.hash(raw_password)

    def check_password(self, raw_password: str) -> bool:
        try:
            return _ph.verify(self.password_hash, raw_password)
        except Exception:
            return False

    def __repr__(self):
        return f"<User {self.email} ({self.role})>"