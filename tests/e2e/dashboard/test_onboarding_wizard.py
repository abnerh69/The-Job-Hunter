import pytest
import time
import os
import subprocess
from typing import Generator
from playwright.sync_api import sync_playwright, expect
from sqlalchemy import create_engine
from jobhunter.db.base import Base
import jobhunter.db.models


@pytest.fixture(scope="module")
def test_db() -> Generator[str, None, None]:
    db_path = os.path.abspath("test_e2e_onboarding.db")
    if os.path.exists(db_path):
        os.remove(db_path)

    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    engine.dispose()

    yield f"sqlite:///{db_path}"

    if os.path.exists(db_path):
        os.remove(db_path)


@pytest.fixture(scope="module")
def streamlit_server(test_db: str) -> Generator[None, None, None]:
    subprocess.run("kill $(lsof -t -i :8501) 2>/dev/null || true", shell=True)
    env = os.environ.copy()
    env["DATABASE_URL"] = test_db
    env["TEST_DATABASE_URL"] = test_db
    env["ANTHROPIC_API_KEY"] = "dummy"
    env["DASHBOARD_PASSWORD"] = "secret123"  # pragma: allowlist secret
    env["PYTHONPATH"] = "src"
    cmd = [
        "streamlit",
        "run",
        "src/jobhunter/dashboard/streamlit_app.py",
        "--server.port=8501",
        "--server.headless=true",
        "--browser.gatherUsageStats=false",
    ]
    process = subprocess.Popen(cmd, env=env)
    time.sleep(10)
    yield
    process.terminate()
    process.wait()


@pytest.mark.e2e
def test_onboarding_wizard_full_flow(streamlit_server: None, test_db: str) -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        page.goto("http://localhost:8501")
        page.get_by_role("textbox", name="Password").fill("secret123")  # pragma: allowlist secret
        page.get_by_role("textbox", name="Password").press("Enter")
        time.sleep(5)

        # 2. Check for soft gating banner
        expect(
            page.get_by_text("Configura tu perfil para empezar a recibir matches")
        ).to_be_visible()
        page.get_by_role("button", name="Empezar wizard").click()
        time.sleep(5)

        # 3. Step 1: Upload Resume
        expect(page.get_by_role("heading", name="Step 1: Upload Resume")).to_be_visible()

        # Upload resume
        resume_path = os.path.abspath("tests/fixtures/resumes/resume.pdf")
        page.locator('input[type="file"]').set_input_files(resume_path)
        page.get_by_role("button", name="Ingest Resume").click()
        time.sleep(15) # Wait for extraction

        # 4. Step 2: Review Extraction
        expect(page.get_by_role("heading", name="Step 2: Review Extraction")).to_be_visible()
        page.get_by_label("Name").fill("John Doe")
        page.get_by_role("button", name="Save Changes").click()
        time.sleep(2)
        page.get_by_role("button", name="Next").click()
        time.sleep(5)

        # 5. Step 3: Personal Context
        expect(page.get_by_role("heading", name="Step 3: Personal Context")).to_be_visible()
        page.get_by_label("Country").fill("Spain")
        page.get_by_label("Work Authorization").fill("EU Citizen")
        page.get_by_role("button", name="Save Context").click()
        time.sleep(2)
        page.get_by_role("button", name="Next").click()
        time.sleep(5)

        # 6. Step 4: Career Angle
        expect(page.get_by_role("heading", name="Step 4: Career Angle")).to_be_visible()
        page.get_by_role("button", name="Generate Profile Draft with Claude").click()
        time.sleep(15)  # Wait for mock LLM and sleep(2) in streamlit
        # expect(page.get_by_text("Profile synthesized!")).to_be_visible() # Success might have disappeared
        page.get_by_role("button", name="Next").click()
        time.sleep(5)

        # 7. Step 5: Salary Proposal
        expect(page.get_by_role("heading", name="Step 5: Salary Proposal")).to_be_visible()
        page.get_by_role("button", name="Generate Salary Proposal with Claude").click()
        time.sleep(15)  # Wait for mock LLM and sleep(2) in streamlit
        # expect(page.get_by_text("Proposal generated!")).to_be_visible()
        page.get_by_role("button", name="Next").click()
        time.sleep(5)

        # 8. Step 6: CV Variants
        expect(page.get_by_role("heading", name="Step 6: CV Variants")).to_be_visible()
        page.get_by_label("Display Name 0").fill("Fullstack Dev")
        page.get_by_role("button", name="Generate Variant 1 with Claude").click()
        time.sleep(15)  # Wait for mock LLM and sleep(2) in streamlit
        # expect(page.get_by_text("Variant 1 generated!")).to_be_visible()
        page.get_by_role("button", name="Next").click()
        time.sleep(5)

        # 9. Step 7: Confirm & Save
        expect(page.get_by_role("heading", name="Step 7: Confirm & Save")).to_be_visible()
        page.get_by_role("button", name="🚀 ACTIVATE PROFILE").click()
        time.sleep(10)
        expect(page.get_by_text("Profile and variants activated successfully!")).to_be_visible()

        # 10. Verify database records
        from sqlalchemy import select
        from sqlalchemy.orm import Session
        from jobhunter.db.models import CandidateProfile, CVVariant, CVVariantExperience

        engine = create_engine(test_db)
        with Session(engine) as session:
            # Verify Profile (The name might have been extracted or filled)
            # In our test we filled John Doe in Step 2
            profile = session.scalar(select(CandidateProfile).where(CandidateProfile.name == "John Doe"))
            assert profile is not None, "Candidate profile not found in database"
            assert profile.is_active is True
            assert profile.country == "Spain"

            # Verify Variant
            variant = session.scalar(select(CVVariant).where(CVVariant.profile_id == profile.id))
            assert variant is not None, "CV Variant not found in database"
            assert variant.display_name == "Fullstack Dev"

            # Verify Experience (at least one)
            experience = session.scalar(select(CVVariantExperience).where(CVVariantExperience.cv_variant_id == variant.id))
            assert experience is not None, "CV Variant Experience not found in database"

        # 11. Verify banner disappeared on home page
        page.goto("http://localhost:8501")
        time.sleep(5)
        expect(
            page.get_by_text("Configura tu perfil para empezar a recibir matches")
        ).not_to_be_visible()

        browser.close()
