from datetime import date, datetime
from typing import Any

from jobhunter.notify.templates import (
    escape_telegram_markdown,
    format_currency,
    format_date_human,
    render,
    truncate_words,
)


def test_format_currency() -> None:
    assert format_currency(5500) == "$5,500"
    assert format_currency(1234.56) == "$1,235"
    assert format_currency(1000000) == "$1,000,000"
    assert format_currency(50, "EUR") == "EUR 50"
    assert format_currency(None) == ""


def test_format_date_human() -> None:
    dt = datetime(2024, 1, 15)
    assert format_date_human(dt) == "Jan 15, 2024"

    d = date(2024, 5, 20)
    assert format_date_human(d) == "May 20, 2024"

    assert format_date_human("2024-12-31T23:59:59Z") == "Dec 31, 2024"
    assert format_date_human("invalid-date") == "invalid-date"
    assert format_date_human("") == ""


def test_truncate_words() -> None:
    text = "This is a very long description that should be truncated"
    assert truncate_words(text, 5) == "This is a very long..."
    assert truncate_words("Short text", 10) == "Short text"
    assert truncate_words("", 5) == ""


def test_escape_telegram_markdown() -> None:
    # Special characters: _ * [ ] ( ) ~ ` > # + - = | { } . !
    input_text = "Special characters: _ * [ ] ( ) ~ ` > # + - = | { } . !"
    expected = r"Special characters: \_ \* \[ \] \( \) \~ \` \> \# \+ \- \= \| \{ \} \. \!"
    assert escape_telegram_markdown(input_text) == expected

    assert escape_telegram_markdown("Normal text") == "Normal text"
    assert escape_telegram_markdown("") == ""


def test_render_tier_a_match_telegram() -> None:
    job = {
        "title": "Senior Python Developer",
        "company": "Tech Corp.",
        "fit_score": 95,
        "url": "https://example.com/job",
        "score_data": {
            "compensation": {
                "salary_min_usd_month": 8000,
                "salary_max_usd_month": 12000,
            },
            "match_analysis": {
                "key_match_points": ["Python Expert", "Remote workflow", "High salary"]
            },
        },
    }
    output = render("notifications/tier_a_match_telegram.md", {"job": job})

    assert "Tier A Match Found" in output
    assert "Senior Python Developer" in output
    assert "Tech Corp\\." in output  # Escaped
    assert "95/100" in output
    assert "$8,000" in output
    assert "$12,000" in output
    assert "Python Expert" in output
    assert "https://example.com/job" in output


def test_render_tier_a_match_email() -> None:
    job = {
        "title": "Flutter Lead",
        "company": "Mobile Inc",
        "fit_score": 88,
        "url": "https://mobile.inc/jobs/1",
        "score_data": {
            "compensation": {
                "salary_min_usd_month": 7000,
            },
            "match_analysis": {"key_match_points": ["Flutter", "Leadership"]},
        },
    }
    output = render("notifications/tier_a_match_email.html", {"job": job})

    assert "Score: 88/100" in output
    assert "Flutter Lead" in output
    assert "Mobile Inc" in output
    assert "$7,000" in output
    assert "<li>Flutter</li>" in output
    assert 'href="https://mobile.inc/jobs/1"' in output


def test_render_weekly_digest_email_html() -> None:
    context = {
        "end_date": "2024-05-26",
        "metrics": {
            "new_jobs": 150,
            "tier_a_count": 5,
            "applications_sent": 3,
        },
        "tier_a_jobs": [
            {"title": "Job 1", "company": "Co 1", "fit_score": 90, "url": "url1"},
        ],
        "pending_tier_b": [],
        "followups_due": [
            {
                "job": {"company": "Target"},
                "next_action": "Follow up email",
                "next_action_due": "2024-05-28",
            }
        ],
    }
    output = render("notifications/weekly_digest_email.html", context)

    assert "Weekly Job Hunt Summary" in output
    assert "May 26, 2024" in output
    assert "150" in output
    assert "Job 1" in output
    assert "Target" in output
    assert "Follow up email" in output
    assert "May 28, 2024" in output


def test_render_weekly_digest_email_txt() -> None:
    context: dict[str, Any] = {
        "end_date": "2024-05-26",
        "metrics": {
            "new_jobs": 150,
            "tier_a_count": 5,
            "applications_sent": 3,
        },
        "tier_a_jobs": [
            {"title": "Job 1", "company": "Co 1", "fit_score": 90, "url": "url1"},
        ],
        "pending_tier_b": [
            {"title": "Job 2", "company": "Co 2", "fit_score": 75},
        ],
        "followups_due": [],
    }
    output = render("notifications/weekly_digest_email.txt", context)

    assert "WEEKLY JOB HUNT SUMMARY" in output
    assert "May 26, 2024" in output
    assert "Job 1" in output
    assert "Job 2" in output
    assert "Co 2" in output
