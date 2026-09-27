"""add_address_phone_email_website_to_organizations

Revision ID: 2f5f3fb343a2
Revises: f39e17b6a0d4
Create Date: 2026-09-27 13:09:07.213659

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '2f5f3fb343a2'
down_revision = 'f39e17b6a0d4'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE organizations ADD COLUMN IF NOT EXISTS address VARCHAR(500)")
    op.execute("ALTER TABLE organizations ADD COLUMN IF NOT EXISTS phone VARCHAR(100)")
    op.execute("ALTER TABLE organizations ADD COLUMN IF NOT EXISTS email VARCHAR(255)")
    op.execute("ALTER TABLE organizations ADD COLUMN IF NOT EXISTS website VARCHAR(255)")


def downgrade():
    op.execute("ALTER TABLE organizations DROP COLUMN IF EXISTS website")
    op.execute("ALTER TABLE organizations DROP COLUMN IF EXISTS email")
    op.execute("ALTER TABLE organizations DROP COLUMN IF EXISTS phone")
    op.execute("ALTER TABLE organizations DROP COLUMN IF EXISTS address")
