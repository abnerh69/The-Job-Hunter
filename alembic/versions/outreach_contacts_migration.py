"""create_outreach_contacts_table

Revision ID: outreach_contacts
Revises: 6fbaf98edf44
Create Date: 2026-04-28 02:09:19

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'outreach_contacts'
down_revision: Union[str, None] = '6fbaf98edf44'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'outreach_contacts',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('company', sa.Text(), nullable=True),
        sa.Column('role', sa.Text(), nullable=True),
        sa.Column('linkedin_url', sa.Text(), nullable=True),
        sa.Column('email', sa.Text(), nullable=True),
        sa.Column('market', sa.String(length=50), nullable=True),
        sa.Column('specialty_stack', sa.String(length=100), nullable=True),
        sa.Column('quality_score', sa.Integer(), nullable=True),
        sa.Column('first_contacted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_contacted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('contact_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('status', sa.String(length=30), server_default='new', nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('linkedin_url')
    )
    op.create_index('idx_outreach_followup', 'outreach_contacts', ['status', 'last_contacted_at'], unique=False)


def downgrade() -> None:
    op.drop_index('idx_outreach_followup', table_name='outreach_contacts')
    op.drop_table('outreach_contacts')
