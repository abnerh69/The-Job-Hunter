"""add_email_messages_table

Revision ID: 99ead058acfc
Revises: 2b3696072a71
Create Date: 2026-04-30 16:49:59.371597

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "99ead058acfc"
down_revision: Union[str, Sequence[str], None] = "2b3696072a71"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "email_messages",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("gmail_message_id", sa.String(length=255), nullable=False),
        sa.Column("gmail_thread_id", sa.String(length=255), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("from_email", sa.String(length=255), nullable=False),
        sa.Column("from_domain", sa.String(length=255), nullable=True),
        sa.Column("subject", sa.Text(), nullable=True),
        sa.Column("snippet", sa.String(length=200), nullable=True),
        sa.Column("body_hash", sa.String(length=64), nullable=False),
        sa.Column("match_status", sa.String(length=30), server_default="unmatched", nullable=False),
        sa.Column("matched_application_id", sa.UUID(), nullable=True),
        sa.Column("matched_outreach_message_id", sa.UUID(), nullable=True),
        sa.Column("match_confidence", sa.Float(), nullable=True),
        sa.Column("match_reasoning", sa.Text(), nullable=True),
        sa.Column(
            "suggested_status_change",
            postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite"),
            nullable=True,
        ),
        sa.Column(
            "processed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "(matched_application_id IS NULL) OR (matched_outreach_message_id IS NULL)",
            name="check_only_one_match_target",
        ),
        sa.ForeignKeyConstraint(
            ["matched_application_id"],
            ["applications.id"],
        ),
        sa.ForeignKeyConstraint(
            ["matched_outreach_message_id"],
            ["outreach_messages.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("gmail_message_id"),
    )
    op.create_index("idx_email_from_domain", "email_messages", ["from_domain"], unique=False)
    op.create_index("idx_email_match_status", "email_messages", ["match_status"], unique=False)
    op.create_index(
        "idx_email_received_at", "email_messages", [sa.text("received_at DESC")], unique=False
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("idx_email_received_at", table_name="email_messages")
    op.drop_index("idx_email_match_status", table_name="email_messages")
    op.drop_index("idx_email_from_domain", table_name="email_messages")
    op.drop_table("email_messages")
