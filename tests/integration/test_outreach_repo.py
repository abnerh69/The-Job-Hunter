import csv
import pytest
from datetime import date, datetime, timedelta
from sqlalchemy.orm import Session

from jobhunter.db.models import OutreachContact
from jobhunter.db.enums import OutreachStatus
from jobhunter.db.repos.outreach import OutreachRepo


@pytest.fixture
def outreach_repo(db_session: Session) -> OutreachRepo:
    return OutreachRepo(db_session)


def test_find_by_linkedin_url(outreach_repo: OutreachRepo) -> None:
    # Given
    url = "https://linkedin.com/in/testuser"
    contact = OutreachContact(name="Test User", linkedin_url=url)
    outreach_repo.create(contact)

    # When
    found = outreach_repo.find_by_linkedin_url(url)
    not_found = outreach_repo.find_by_linkedin_url("https://linkedin.com/in/other")

    # Then
    assert found is not None
    assert found.name == "Test User"
    assert not_found is None


def test_list_due_for_followup(outreach_repo: OutreachRepo, db_session: Session) -> None:
    # Given
    today = date(2024, 1, 15)

    # Contacted 8 days ago -> Due
    c1 = OutreachContact(name="C1", status=OutreachStatus.CONTACTED,
                         last_contacted_at=datetime(2024, 1, 7, 12, 0))
    # Contacted 5 days ago -> Not due
    c2 = OutreachContact(name="C2", status=OutreachStatus.CONTACTED,
                         last_contacted_at=datetime(2024, 1, 10, 12, 0))
    # New -> Not due
    c3 = OutreachContact(name="C3", status=OutreachStatus.NEW)

    db_session.add_all([c1, c2, c3])
    db_session.flush()

    # When
    due = outreach_repo.list_due_for_followup(today)

    # Then
    assert len(due) == 1
    assert due[0].name == "C1"


def test_mark_contacted(outreach_repo: OutreachRepo) -> None:
    # Given
    contact = OutreachContact(name="Test User", status=OutreachStatus.NEW)
    outreach_repo.create(contact)
    contact_id = contact.id

    # When
    outreach_repo.mark_contacted(contact_id)

    # Then
    updated = outreach_repo.get(contact_id)
    assert updated.status == OutreachStatus.CONTACTED
    assert updated.contact_count == 1
    assert updated.first_contacted_at is not None
    assert updated.last_contacted_at is not None

    # When mark again
    first_time = updated.first_contacted_at
    outreach_repo.mark_contacted(contact_id)

    # Then
    updated = outreach_repo.get(contact_id)
    assert updated.contact_count == 2
    assert updated.first_contacted_at == first_time


def test_bulk_import_from_csv(outreach_repo: OutreachRepo, tmp_path: pytest.TempPathFactory) -> None:
    # Given
    csv_file = tmp_path / "contacts.csv"
    content = [
        "name,linkedin_url,company,role,quality_score",
        "Alice,https://linkedin.com/in/alice,TechCo,Recruiter,5",
        "Bob,https://linkedin.com/in/bob,SoftInc,Manager,4",
        "Alice Duplicate,https://linkedin.com/in/alice,Other,Other,1",
        "Invalid,,NoURL,,",
    ]
    csv_file.write_text("\n".join(content))

    # When
    imported, skipped = outreach_repo.bulk_import_from_csv(str(csv_file))

    # Then
    assert imported == 2
    assert skipped == 1 # Alice Duplicate

    alice = outreach_repo.find_by_linkedin_url("https://linkedin.com/in/alice")
    assert alice.name == "Alice"
    assert alice.quality_score == 5


def test_bulk_import_from_csv_malformed(outreach_repo: OutreachRepo, tmp_path: pytest.TempPathFactory) -> None:
    # Given a CSV that might cause issues (though csv.DictReader is quite lenient)
    csv_file = tmp_path / "malformed.csv"
    # An empty file or one with only headers is not "malformed" but "empty"
    csv_file.write_text("name;linkedin_url\nAlice;url1") # Wrong delimiter for DictReader default

    # When
    imported, skipped = outreach_repo.bulk_import_from_csv(str(csv_file))

    # Then
    # DictReader will treat the whole line as one key "name;linkedin_url"
    assert imported == 0
    assert skipped == 0
