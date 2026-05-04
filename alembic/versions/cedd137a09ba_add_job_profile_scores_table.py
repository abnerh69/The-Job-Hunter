"""add_job_profile_scores_table

Revision ID: cedd137a09ba
Revises: 6bc219d83275
Create Date: 2026-05-03 07:26:29.303234

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "cedd137a09ba"
down_revision: Union[str, Sequence[str], None] = "6bc219d83275"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "job_profile_scores",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("job_id", sa.UUID(), nullable=False),
        sa.Column("profile_id", sa.UUID(), nullable=False),
        sa.Column("fit_score", sa.Integer(), nullable=True),
        sa.Column("tier", sa.String(length=10), nullable=True),
        sa.Column(
            "score_data",
            postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite"),
            nullable=True,
        ),
        sa.Column(
            "scored_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("scored_with_prompt_version", sa.String(length=20), nullable=True),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["profile_id"], ["candidate_profiles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_job_profile_scores_job_id", "job_profile_scores", ["job_id"], unique=False)
    op.create_index(
        "idx_job_profile_scores_profile_id", "job_profile_scores", ["profile_id"], unique=False
    )
    op.create_index("idx_job_profile_scores_tier", "job_profile_scores", ["tier"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("idx_job_profile_scores_tier", table_name="job_profile_scores")
    op.drop_index("idx_job_profile_scores_profile_id", table_name="job_profile_scores")
    op.drop_index("idx_job_profile_scores_job_id", table_name="job_profile_scores")
    op.drop_table("job_profile_scores")
