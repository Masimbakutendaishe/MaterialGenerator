"""PasswordResetRequest — tracks forgot-password requests requiring admin approval and a one-time code."""
import uuid
import secrets
from datetime import datetime, timezone, timedelta
from argon2 import PasswordHasher
from app.extensions import db

_ph = PasswordHasher()

# pending -> approved -> used (or expired)
STATUSES = ("pending", "approved", "used", "expired", "denied")


class PasswordResetRequest(db.Model):
    __tablename__ = "password_reset_requests"

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=False)
    status = db.Column(db.String(20), nullable=False, default="pending")
    otp_hash = db.Column(db.String(255), nullable=True)
    otp_expires_at = db.Column(db.DateTime, nullable=True)
    approved_by_user_id = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    user = db.relationship("User", foreign_keys=[user_id])

    def generate_otp(self) -> str:
        """Generates a 6-digit OTP, stores its hash, sets 30-minute expiry. Returns the
        plaintext code ONCE so the admin can relay it — it is never stored in plaintext."""
        code = f"{secrets.randbelow(1000000):06d}"
        self.otp_hash = _ph.hash(code)
        self.otp_expires_at = datetime.now(timezone.utc) + timedelta(minutes=30)
        return code

    def verify_otp(self, code: str) -> bool:
        if not self.otp_hash or self.status != "approved":
            return False
        if self.otp_expires_at and datetime.now(timezone.utc) > self.otp_expires_at.replace(tzinfo=timezone.utc):
            return False
        try:
            return _ph.verify(self.otp_hash, code)
        except Exception:
            return False