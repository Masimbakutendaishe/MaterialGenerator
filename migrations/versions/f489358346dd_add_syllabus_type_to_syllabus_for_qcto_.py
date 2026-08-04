"""add syllabus_type to syllabus for QCTO support

Revision ID: f489358346dd
Revises: c03da14ddcd1
Create Date: 2026-08-04 14:46:29.271301

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f489358346dd'
down_revision = 'c03da14ddcd1'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('syllabi', schema=None) as batch_op:
        batch_op.add_column(sa.Column('syllabus_type', sa.String(length=50), nullable=False, server_default='standard'))


def downgrade():
    with op.batch_alter_table('syllabi', schema=None) as batch_op:
        batch_op.drop_column('syllabus_type')