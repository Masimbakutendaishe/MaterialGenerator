"""MaterialReview — tracks the QA approval status of a generated material.
ReviewComment — threaded feedback tied to a review.
Notification — simple in-app notification, polled by the recipient."""
import uuid
from datetime import datetime, timezone
from app.extensions import db

# pending_review -> changes_requested -> pending_review (resubmit) -> approved
REVIEW_STATUSES = ("pending_review", "changes_requested", "approved")


class MaterialReview(db.Model):
    __tablename__ = "material_reviews"

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    generation_job_id = db.Column(db.String(36), db.ForeignKey("generation_jobs.id"), nullable=False, unique=True)
    organization_id = db.Column(db.String(36), db.ForeignKey("organizations.id"), nullable=False)
    submitted_by_user_id = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=False)
    reviewer_user_id = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=True)  # who it's assigned to

    status = db.Column(db.String(50), nullable=False, default="pending_review")

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    comments = db.relationship("ReviewComment", backref="review", cascade="all, delete-orphan", order_by="ReviewComment.created_at")

    def __repr__(self):
        return f"<MaterialReview {self.id} {self.status}>"


class ReviewComment(db.Model):
    __tablename__ = "review_comments"

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    review_id = db.Column(db.String(36), db.ForeignKey("material_reviews.id"), nullable=False)
    author_user_id = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=False)
    body = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return f"<ReviewComment {self.id}>"


class Notification(db.Model):
    __tablename__ = "notifications"

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    recipient_user_id = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=False)
    message = db.Column(db.String(500), nullable=False)
    link_review_id = db.Column(db.String(36), db.ForeignKey("material_reviews.id"), nullable=True)
    is_read = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    link_job_id = db.Column(db.String(36), db.ForeignKey("generation_jobs.id"), nullable=True)

    def __repr__(self):
        return f"<Notification {self.id} read={self.is_read}>"

def prune_old_notifications(recipient_user_id: str, keep: int = 20):
    """Deletes a user's oldest notifications beyond the most recent `keep` count."""
    from app.extensions import db
    ids_to_keep = [
        n.id for n in Notification.query.filter_by(recipient_user_id=recipient_user_id)
        .order_by(Notification.created_at.desc()).limit(keep).all()
    ]
    if ids_to_keep:
        Notification.query.filter(
            Notification.recipient_user_id == recipient_user_id,
            ~Notification.id.in_(ids_to_keep)
        ).delete(synchronize_session=False)