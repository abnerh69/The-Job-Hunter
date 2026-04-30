import pytest
from datetime import date, datetime, timedelta
from typing import Generator
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from jobhunter.db.base import Base
from jobhunter.db.models import OutreachContact
from jobhunter.db.enums import OutreachStatus, OutreachMarket
from jobhunter.db.repos.outreach import OutreachRepo


@pytest.fixture
def session() -> Generator[Session, None, None]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session_factory = sessionmaker(bind=engine)
    session = Session_factory()
    yield session
    session.close()


def test_list_contacts_filtering(session: Session) -> None:
    repo = OutreachRepo(session)

    # Create test data
    c1 = OutreachContact(
        name="John Doe",
        company="Google",
        market=OutreachMarket.GERMANY,
        status=OutreachStatus.NEW,
        quality_score=10,
        specialty_stack="Python, AI",
    )
    c2 = OutreachContact(
        name="Jane Smith",
        company="Meta",
        market=OutreachMarket.UK,
        status=OutreachStatus.CONTACTED,
        last_contacted_at=datetime.now() - timedelta(days=10),
        quality_score=8,
        specialty_stack="Flutter",
    )
    c3 = OutreachContact(
        name="Bob Brown",
        company="Amazon",
        market=OutreachMarket.EU_WIDE,
        status=OutreachStatus.WARM,
        quality_score=9,
        specialty_stack="Backend",
    )

    session.add_all([c1, c2, c3])
    session.commit()

    # Filter by status
    contacts = repo.list_contacts(statuses=[OutreachStatus.NEW])
    assert len(contacts) == 1
    assert contacts[0].name == "John Doe"

    # Filter by market
    contacts = repo.list_contacts(markets=[OutreachMarket.UK])
    assert len(contacts) == 1
    assert contacts[0].name == "Jane Smith"

    # Filter by stack
    contacts = repo.list_contacts(stacks=["Python"])
    assert len(contacts) == 1
    assert contacts[0].name == "John Doe"

    # Filter by due for follow-up
    contacts = repo.list_contacts(due_for_followup=True, today=date.today())
    assert len(contacts) == 1
    assert contacts[0].name == "Jane Smith"


def test_get_outreach_metrics(session: Session) -> None:
    repo = OutreachRepo(session)

    c1 = OutreachContact(name="C1", status=OutreachStatus.NEW, last_contacted_at=None)
    c2 = OutreachContact(
        name="C2",
        status=OutreachStatus.CONTACTED,
        last_contacted_at=datetime.now() - timedelta(days=8),
    )
    c3 = OutreachContact(
        name="C3",
        status=OutreachStatus.CONTACTED,
        last_contacted_at=datetime.now() - timedelta(days=2),
    )

    session.add_all([c1, c2, c3])
    session.commit()

    metrics = repo.get_outreach_metrics(today=date.today())

    assert metrics["total"] == 3
    assert metrics["status_new"] == 1
    assert metrics["status_contacted"] == 2
    assert metrics["pending_followups"] == 1
