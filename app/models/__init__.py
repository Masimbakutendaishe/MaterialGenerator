"""Import all models here so Flask-Migrate can discover them."""
from app.models.organization import Organization
from app.models.user import User
from app.models.syllabus import Syllabus
from app.models.generation_job import GenerationJob
from app.models.review import MaterialReview, ReviewComment, Notification