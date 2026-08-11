"""add plans table and organization plan_id

Revision ID: d561d941f35e
Revises: f489358346dd
Create Date: [leave as auto-generated]

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd561d941f35e'
down_revision = 'f489358346dd'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('plans',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('monthly_package_limit', sa.Integer(), nullable=True),
        sa.Column('monthly_document_limit', sa.Integer(), nullable=True),
        sa.Column('price_zar', sa.Integer(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.add_column('organizations', sa.Column('plan_id', sa.String(length=36), nullable=True))
    op.create_foreign_key('organizations_plan_id_fkey', 'organizations', 'plans', ['plan_id'], ['id'])


def downgrade():
    op.drop_constraint('organizations_plan_id_fkey', 'organizations', type_='foreignkey')
    op.drop_column('organizations', 'plan_id')
    op.drop_table('plans')