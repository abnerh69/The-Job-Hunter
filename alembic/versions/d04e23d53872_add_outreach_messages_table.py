"""add_outreach_messages_table

Revision ID: d04e23d53872
Revises: f2fcceef4fa7
Create Date: 2026-04-30 12:40:34.629099

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d04e23d53872"
down_revision: Union[str, Sequence[str], None] = "f2fcceef4fa7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "outreach_messages",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("contact_id", sa.UUID(), nullable=False),
        sa.Column("template_type", sa.String(length=50), nullable=False),
        sa.Column("template_version", sa.String(length=20), nullable=True),
        sa.Column("subject", sa.Text(), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("body_edited_by_user", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("research_notes", sa.Text(), nullable=True),
        sa.Column("model_used", sa.String(length=50), nullable=True),
        sa.Column("cost_usd", sa.Numeric(precision=10, scale=6), nullable=True),
        sa.Column("status", sa.String(length=30), server_default="draft", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("replied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("parent_message_id", sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(["contact_id"], ["outreach_contacts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["parent_message_id"],
            ["outreach_messages.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("outreach_messages", schema=None) as batch_op:
        batch_op.create_index(
            "idx_outreach_messages_contact_created",
            ["contact_id", "created_at"],
            unique=False,
        )
        batch_op.create_index(
            "idx_outreach_messages_status_sent",
            ["status", "sent_at"],
            unique=False,
            postgresql_where=sa.text("status IN ('sent', 'draft')"),
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("outreach_messages", schema=None) as batch_op:
        batch_op.drop_index(
            "idx_outreach_messages_status_sent",
            postgresql_where=sa.text("status IN ('sent', 'draft')"),
        )
        batch_op.drop_index("idx_outreach_messages_contact_created")

    op.drop_table("outreach_messages")
