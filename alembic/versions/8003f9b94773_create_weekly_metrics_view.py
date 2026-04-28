"""create_weekly_metrics_view

Revision ID: 8003f9b94773
Revises: outreach_contacts
Create Date: 2026-04-28 02:54:30.221745

"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "8003f9b94773"
down_revision: Union[str, Sequence[str], None] = "outreach_contacts"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("""
        CREATE MATERIALIZED VIEW weekly_metrics AS
        SELECT
            date_trunc('week', applied_at)::date AS week,
            COUNT(*) AS apps_sent,
            COUNT(*) FILTER (WHERE status NOT IN ('applied', 'ghosted', 'withdrawn')) AS apps_with_response,
            COUNT(*) FILTER (WHERE status IN ('screening', 'interview_1', 'interview_n', 'offer')) AS interviews,
            COUNT(*) FILTER (WHERE status = 'offer') AS offers,
            AVG(salary_offered_max) FILTER (WHERE status = 'offer') AS avg_offer_max
        FROM applications
        GROUP BY 1
    """)
    op.execute("CREATE UNIQUE INDEX idx_weekly_metrics_week ON weekly_metrics (week)")


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP MATERIALIZED VIEW IF EXISTS weekly_metrics")
