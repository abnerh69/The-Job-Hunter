import pytest
import time
import os
import subprocess
from typing import Generator
from playwright.sync_api import sync_playwright, expect


@pytest.fixture(scope="module", autouse=True)
def streamlit_server() -> Generator[None, None, None]:
    # Kill any existing streamlit server on 8501
    subprocess.run("kill $(lsof -t -i :8501) 2>/dev/null || true", shell=True)

    # Setup environment
    env = os.environ.copy()
    env["ANTHROPIC_API_KEY"] = "dummy"
    env["DASHBOARD_PASSWORD"] = "secret123"
    env["PYTHONPATH"] = "src"

    # Run streamlit
    cmd = [
        "uv",
        "run",
        "streamlit",
        "run",
        "src/jobhunter/dashboard/streamlit_app.py",
        "--server.port=8501",
        "--server.headless=true",
        "--browser.gatherUsageStats=false",
    ]
    process = subprocess.Popen(cmd, env=env)

    # Wait for server to start
    time.sleep(7)

    yield

    # Kill server
    process.terminate()
    process.wait()


def test_login_flow() -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        page.goto("http://localhost:8501", wait_until="networkidle")

        # Check if we are at login screen
        expect(page.get_by_role("textbox", name="Password")).to_be_visible()

        # Try wrong password
        page.get_by_role("textbox", name="Password").fill("wrong")
        page.get_by_role("textbox", name="Password").press("Enter")
        time.sleep(1)
        expect(page.get_by_text("Password incorrect")).to_be_visible()

        # Try correct password
        page.get_by_role("textbox", name="Password").fill("secret123")
        page.get_by_role("textbox", name="Password").press("Enter")
        time.sleep(2)

        # Should see the dashboard
        expect(page.get_by_text("Automated job search system")).to_be_visible()
        expect(page.get_by_text("System Status")).to_be_visible()

        browser.close()


def test_page_protection() -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        # Try to access a page directly
        page.goto("http://localhost:8501/New_Matches")
        time.sleep(2)

        # Should be redirected or shown login
        expect(page.get_by_role("textbox", name="Password")).to_be_visible()

        browser.close()


def test_logout() -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        # Login first
        page.goto("http://localhost:8501")
        page.get_by_role("textbox", name="Password").fill("secret123")
        page.get_by_role("textbox", name="Password").press("Enter")
        time.sleep(2)

        # Click logout
        page.get_by_role("button", name="Logout").click()
        time.sleep(1)

        # Should be back at login
        expect(page.get_by_role("textbox", name="Password")).to_be_visible()

        browser.close()
