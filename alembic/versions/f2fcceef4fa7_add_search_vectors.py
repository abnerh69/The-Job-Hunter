"""add_search_vectors

Revision ID: f2fcceef4fa7
Revises: 4c9f4a2b6f09
Create Date: 2026-04-30 07:14:35.081450

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f2fcceef4fa7"
down_revision: Union[str, Sequence[str], None] = "4c9f4a2b6f09"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    if op.get_context().dialect.name == "postgresql":
        # Add tsvector columns as GENERATED ALWAYS AS
        # Postgres 12+ supports GENERATED ALWAYS AS for stored columns

        # Jobs: title, company, description
        op.execute(
            """
            ALTER TABLE jobs
            ADD COLUMN search_vector tsvector
            GENERATED ALWAYS AS (
                setweight(to_tsvector('english', coalesce(title, '')), 'A') ||
                setweight(to_tsvector('english', coalesce(company, '')), 'B') ||
                setweight(to_tsvector('english', coalesce(description, '')), 'C')
            ) STORED
            """
        )
        op.execute("CREATE INDEX idx_jobs_search_vector ON jobs USING GIN (search_vector)")

        # Applications: notes
        op.execute(
            """
            ALTER TABLE applications
            ADD COLUMN search_vector tsvector
            GENERATED ALWAYS AS (
                to_tsvector('english', coalesce(notes, ''))
            ) STORED
            """
        )
        op.execute("CREATE INDEX idx_apps_search_vector ON applications USING GIN (search_vector)")

        # Outreach Contacts: name, company
        op.execute(
            """
            ALTER TABLE outreach_contacts
            ADD COLUMN search_vector tsvector
            GENERATED ALWAYS AS (
                setweight(to_tsvector('english', coalesce(name, '')), 'A') ||
                setweight(to_tsvector('english', coalesce(company, '')), 'B')
            ) STORED
            """
        )
        op.execute(
            "CREATE INDEX idx_outreach_search_vector ON outreach_contacts USING GIN (search_vector)"
        )


def downgrade() -> None:
    """Downgrade schema."""
    if op.get_context().dialect.name == "postgresql":
        op.drop_index("idx_outreach_search_vector", table_name="outreach_contacts")
        op.drop_column("outreach_contacts", "search_vector")

        op.drop_index("idx_apps_search_vector", table_name="applications")
        op.drop_column("applications", "search_vector")

        op.drop_index("idx_jobs_search_vector", table_name="jobs")
        op.drop_column("jobs", "search_vector")
