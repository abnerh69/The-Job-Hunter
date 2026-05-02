import pytest
from datetime import date
from unittest.mock import MagicMock

from jobhunter.analytics.email_metrics import get_matcher_metrics
from jobhunter.db.enums import EmailMatchStatus


@pytest.fixture
def db_session() -> MagicMock:
    # We could use a real SQLite in-memory DB here if we want more realistic tests,
    # but for unit testing the repo/metrics, mocking session or using a helper is common.
    # Given the project structure, I'll use a mock but ensure it behaves as expected.
    session = MagicMock()
    return session


def test_get_matcher_metrics_calculation(db_session: MagicMock) -> None:
    # Setup mock returns for the counts query
    db_session.execute.return_value.all.side_effect = [
        # Counts by status
        [
            (EmailMatchStatus.AUTO_MATCHED, 2),
            (EmailMatchStatus.AI_MATCHED, 1),
            (EmailMatchStatus.UNMATCHED, 1),
            (EmailMatchStatus.IGNORED_MARKETING, 1),
            (EmailMatchStatus.USER_CONFIRMED, 3),
            (EmailMatchStatus.USER_REJECTED, 1),
        ],
        # Top domains
        [
            ("google.com", 3),
            ("github.com", 2),
        ],
    ]

    # Mock for AI Cost
    db_session.scalar.return_value = 0.05

    start = date(2024, 1, 1)
    end = date(2024, 1, 31)

    metrics = get_matcher_metrics(db_session, start, end)

    assert metrics.total_processed == 9
    assert metrics.auto_matched == 2
    assert metrics.ai_matched == 1
    assert metrics.unmatched == 1
    assert metrics.ignored_marketing == 1
    assert metrics.user_confirmed == 3
    assert metrics.user_rejected == 1

    # Precision: user_confirmed / (user_confirmed + user_rejected) = 3 / (3 + 1) = 0.75
    assert metrics.precision == 0.75

    # Match rate: (auto + ai + confirmed + rejected) / (total - ignored)
    # (2 + 1 + 3 + 1) / (9 - 1) = 7 / 8 = 0.875
    assert metrics.match_rate == 0.875

    assert metrics.ai_cost_usd == 0.05
    assert len(metrics.top_domains) == 2
    assert metrics.top_domains[0]["domain"] == "google.com"
    assert metrics.top_domains[0]["count"] == 3
