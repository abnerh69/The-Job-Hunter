"""create_source_health_table

Revision ID: 4c73a58d9d21
Revises: 8003f9b94773
Create Date: 2026-04-28 15:40:19.337345

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "4c73a58d9d21"
down_revision: Union[str, Sequence[str], None] = "8003f9b94773"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "source_health",
        sa.Column("source_name", sa.String(length=50), nullable=False),
        sa.Column("state", sa.String(length=20), server_default="closed", nullable=False),
        sa.Column("failure_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_failure_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("opened_until", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("source_name"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("source_health")
