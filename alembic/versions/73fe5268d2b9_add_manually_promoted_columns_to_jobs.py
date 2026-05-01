"""add manually promoted columns to jobs

Revision ID: 73fe5268d2b9
Revises: cb5c9f0689f4
Create Date: 2026-05-01 03:30:28.063691

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '73fe5268d2b9'
down_revision: Union[str, Sequence[str], None] = 'cb5c9f0689f4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('jobs', sa.Column('manually_promoted_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('jobs', sa.Column('manually_promoted_reason', sa.Text(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('jobs', 'manually_promoted_reason')
    op.drop_column('jobs', 'manually_promoted_at')
