import pytest
from unittest.mock import MagicMock, AsyncMock
from jobhunter.outreach.linkedin_csv import LinkedInCSVParser
from jobhunter.outreach.scoring import (
    infer_market,
    infer_specialty_stack,
    calculate_heuristic_score,
    enrich_contact_with_ai,
)
from jobhunter.db.enums import OutreachMarket
from jobhunter.db.models import OutreachContact


def test_linkedin_csv_parsing() -> None:
    csv_content = """First Name,Last Name,URL,Email Address,Company,Position,Connected On
Jane,Doe,https://www.linkedin.com/in/janedoe,jane@example.com,Zalando,Tech Recruiter,2023-10-26
John,Smith,https://www.linkedin.com/in/johnsmith,,Google,Software Engineer,2023-10-25
"""
    contacts = LinkedInCSVParser.parse(csv_content)
    assert len(contacts) == 2
    assert contacts[0]["name"] == "Jane Doe"
    assert contacts[0]["linkedin_url"] == "https://www.linkedin.com/in/janedoe"
    assert contacts[0]["role"] == "Tech Recruiter"
    assert contacts[0]["company"] == "Zalando"
    assert contacts[1]["name"] == "John Smith"


def test_linkedin_csv_parsing_missing_url() -> None:
    csv_content = """First Name,Last Name,URL,Email Address,Company,Position,Connected On
Jane,Doe,,jane@example.com,Zalando,Tech Recruiter,2023-10-26
"""
    contacts = LinkedInCSVParser.parse(csv_content)
    assert len(contacts) == 0


def test_infer_market() -> None:
    assert infer_market("Acme GmbH", None) == OutreachMarket.GERMANY
    assert infer_market("Tech Ltd", None) == OutreachMarket.UK
    assert infer_market("Dutch N.V.", None) == OutreachMarket.NETHERLANDS
    assert infer_market("Global Corp", "Berlin based") == OutreachMarket.GERMANY
    assert infer_market("Generic Corp", None) == OutreachMarket.EU_WIDE


def test_infer_specialty_stack() -> None:
    stack_python = infer_specialty_stack("Senior Python Developer")
    assert stack_python is not None and "Python" in stack_python

    stack_ai = infer_specialty_stack("ML Engineer")
    assert stack_ai is not None and "AI/ML" in stack_ai

    stack_flutter = infer_specialty_stack("Flutter Developer")
    assert stack_flutter is not None and "Flutter" in stack_flutter

    assert infer_specialty_stack("Accountant") is None


def test_heuristic_scoring() -> None:
    profile = {"primary_stack": ["Python", "AI/ML"]}

    # Recruiter + AI-friendly DACH + Stack match = 1 (base) + 2 + 1 + 1 = 5
    contact1 = OutreachContact(
        name="Jane", role="Tech Recruiter", company="Zalando", specialty_stack="Python, AI/ML"
    )
    assert calculate_heuristic_score(contact1, profile) == 5

    # CTO = 1 + 2 = 3
    contact2 = OutreachContact(name="John", role="CTO", company="Other", specialty_stack="Java")
    assert calculate_heuristic_score(contact2, profile) == 3

    # Random person = 1
    contact3 = OutreachContact(name="Bob", role="Chef", company="Kitchen", specialty_stack="Knives")
    assert calculate_heuristic_score(contact3, profile) == 1


@pytest.mark.asyncio
async def test_enrich_with_ai() -> None:
    mock_llm = AsyncMock()
    mock_llm.complete.return_value = MagicMock(text="4", cost_usd=0.001)

    contact = OutreachContact(name="Jane", role="Recruiter", company="Zalando")
    session = MagicMock()

    score = await enrich_contact_with_ai(contact, mock_llm, session)
    assert score == 4
    mock_llm.complete.assert_called_once()
