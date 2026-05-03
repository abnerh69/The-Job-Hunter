"""add_candidate_profile_schema

Revision ID: 6bc219d83275
Revises: 0d3bfea9fc9e
Create Date: 2026-05-03 01:22:06.147155

"""

from typing import Any, Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "6bc219d83275"
down_revision: Union[str, Sequence[str], None] = "0d3bfea9fc9e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    is_postgres = op.get_context().dialect.name == "postgresql"

    # Define types based on dialect
    uuid_type: Any
    array_text_type: Any
    jsonb_type: Any

    if is_postgres:
        uuid_type = postgresql.UUID(as_uuid=True)
        array_text_type = postgresql.ARRAY(sa.Text())
        jsonb_type = postgresql.JSONB(astext_type=sa.Text())
    else:
        uuid_type = sa.UUID(as_uuid=True)
        array_text_type = sa.JSON()  # Fallback for SQLite
        jsonb_type = sa.JSON()

    # 1. Table: candidate_profiles
    op.create_table(
        "candidate_profiles",
        sa.Column(
            "id",
            uuid_type,
            server_default=sa.text("gen_random_uuid()") if is_postgres else None,
            nullable=False,
            default=sa.text("(uuid_generate_v4())") if not is_postgres else None,
        ),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=True),
        sa.Column("seniority", sa.String(length=50), nullable=True),
        sa.Column("years_experience", sa.Integer(), nullable=True),
        sa.Column("country", sa.String(length=50), nullable=True),
        sa.Column("work_authorization", sa.Text(), nullable=True),
        sa.Column("timezone_home", sa.String(length=50), nullable=True),
        sa.Column("overlap_max_hours_cet", sa.Integer(), nullable=True),
        sa.Column("preferred_overlap_cet", sa.Integer(), nullable=True),
        sa.Column("primary_stack", array_text_type, nullable=True),
        sa.Column("secondary_stack", array_text_type, nullable=True),
        sa.Column("domains", array_text_type, nullable=True),
        sa.Column("languages", jsonb_type, nullable=True),
        sa.Column("compensation", jsonb_type, nullable=True),
        sa.Column("contract_preferences", array_text_type, nullable=True),
        sa.Column("hard_blockers", array_text_type, nullable=True),
        sa.Column("soft_negatives", array_text_type, nullable=True),
        sa.Column("positive_signals", array_text_type, nullable=True),
        sa.Column("payment_methods_ok", array_text_type, nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()") if is_postgres else sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()") if is_postgres else sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    if is_postgres:
        op.create_index(
            "idx_profiles_is_active",
            "candidate_profiles",
            ["is_active"],
            unique=False,
            postgresql_where=sa.text("is_active = true"),
        )

    # 2. Table: candidate_profile_history
    op.create_table(
        "candidate_profile_history",
        sa.Column(
            "id",
            uuid_type,
            server_default=sa.text("gen_random_uuid()") if is_postgres else None,
            nullable=False,
        ),
        sa.Column("profile_id", uuid_type, nullable=False),
        sa.Column("snapshot", jsonb_type, nullable=False),
        sa.Column(
            "changed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()") if is_postgres else sa.func.now(),
            nullable=False,
        ),
        sa.Column("changed_by", sa.String(length=100), nullable=True),
        sa.Column("change_reason", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["profile_id"], ["candidate_profiles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_profile_history_profile_id_changed_at",
        "candidate_profile_history",
        ["profile_id", sa.text("changed_at DESC")],
        unique=False,
    )

    # 3. Table: cv_variants
    op.create_table(
        "cv_variants",
        sa.Column(
            "id",
            uuid_type,
            server_default=sa.text("gen_random_uuid()") if is_postgres else None,
            nullable=False,
        ),
        sa.Column("profile_id", uuid_type, nullable=False),
        sa.Column("name", sa.String(length=50), nullable=False),
        sa.Column("display_name", sa.String(length=100), nullable=True),
        sa.Column("target_role_keywords", array_text_type, nullable=True),
        sa.Column("target_stack", array_text_type, nullable=True),
        sa.Column("target_seniority", sa.String(length=50), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("skills", array_text_type, nullable=True),
        sa.Column("raw_markdown", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()") if is_postgres else sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()") if is_postgres else sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["profile_id"], ["candidate_profiles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("profile_id", "name"),
    )
    op.create_index("idx_cv_variants_profile_id", "cv_variants", ["profile_id"], unique=False)

    # 4. Table: cv_variant_experiences
    op.create_table(
        "cv_variant_experiences",
        sa.Column(
            "id",
            uuid_type,
            server_default=sa.text("gen_random_uuid()") if is_postgres else None,
            nullable=False,
        ),
        sa.Column("cv_variant_id", uuid_type, nullable=False),
        sa.Column("role", sa.String(length=200), nullable=True),
        sa.Column("company", sa.String(length=200), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("bullets", array_text_type, nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["cv_variant_id"], ["cv_variants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_cv_exp_variant_sort",
        "cv_variant_experiences",
        ["cv_variant_id", "sort_order"],
        unique=False,
    )

    # 5. SQL Trigger for history
    if is_postgres:
        op.execute(
            """
            CREATE OR REPLACE FUNCTION candidate_profile_snapshot_trigger_fn()
            RETURNS TRIGGER AS $$
            BEGIN
                IF (OLD IS DISTINCT FROM NEW) THEN
                    INSERT INTO candidate_profile_history (id, profile_id, snapshot, changed_by, change_reason)
                    VALUES (gen_random_uuid(), OLD.id, to_jsonb(OLD), 'db_trigger', NEW.notes);
                END IF;
                NEW.updated_at = now();
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;
            """
        )
        op.execute(
            """
            CREATE TRIGGER trg_candidate_profile_history
            BEFORE UPDATE ON candidate_profiles
            FOR EACH ROW
            EXECUTE FUNCTION candidate_profile_snapshot_trigger_fn();
            """
        )


def downgrade() -> None:
    """Downgrade schema."""
    is_postgres = op.get_context().dialect.name == "postgresql"

    if is_postgres:
        op.execute("DROP TRIGGER IF EXISTS trg_candidate_profile_history ON candidate_profiles")
        op.execute("DROP FUNCTION IF EXISTS candidate_profile_snapshot_trigger_fn")

    op.drop_index("idx_cv_exp_variant_sort", table_name="cv_variant_experiences")
    op.drop_table("cv_variant_experiences")

    op.drop_index("idx_cv_variants_profile_id", table_name="cv_variants")
    op.drop_table("cv_variants")

    op.drop_index(
        "idx_profile_history_profile_id_changed_at", table_name="candidate_profile_history"
    )
    op.drop_table("candidate_profile_history")

    if is_postgres:
        op.drop_index("idx_profiles_is_active", table_name="candidate_profiles")
    op.drop_table("candidate_profiles")
