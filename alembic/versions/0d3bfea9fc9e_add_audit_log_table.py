"""add_audit_log_table

Revision ID: 0d3bfea9fc9e
Revises: 72ef8867ac56
Create Date: 2026-05-03 00:43:29.055350

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0d3bfea9fc9e"
down_revision: Union[str, Sequence[str], None] = "72ef8867ac56"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "audit_log",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("event_type", sa.String(length=50), nullable=False),
        sa.Column("actor", sa.String(length=255), nullable=False),
        sa.Column("target_entity", sa.String(length=50), nullable=True),
        sa.Column("target_id", sa.UUID(), nullable=True),
        sa.Column("action", sa.String(length=255), nullable=False),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite"),
            nullable=True,
        ),
        sa.Column("ip_address", sa.String(length=45), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_audit_actor_time", "audit_log", ["actor", sa.text("created_at DESC")], unique=False
    )
    op.create_index(
        "idx_audit_event_time",
        "audit_log",
        ["event_type", sa.text("created_at DESC")],
        unique=False,
    )
    op.create_index("idx_audit_target", "audit_log", ["target_entity", "target_id"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("idx_audit_target", table_name="audit_log")
    op.drop_index("idx_audit_event_time", table_name="audit_log")
    op.drop_index("idx_audit_actor_time", table_name="audit_log")
    op.drop_table("audit_log")
