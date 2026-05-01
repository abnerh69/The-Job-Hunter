import time
import os
import subprocess
from typing import Generator
import pytest
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


def test_metrics_page_renders() -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        # Login
        page.goto("http://localhost:8501")
        page.get_by_role("textbox", name="Password").fill("secret123")
        page.get_by_role("textbox", name="Password").press("Enter")
        time.sleep(2)

        # Navigate to Metrics page
        page.get_by_role("link", name="Metrics").click()
        time.sleep(3)

        # Check header
        expect(page.get_by_text("Metrics & Insights")).to_be_visible()

        # Check tabs
        expect(page.get_by_role("tab", name="Funnel")).to_be_visible()
        expect(page.get_by_role("tab", name="Sources")).to_be_visible()
        expect(page.get_by_role("tab", name="Trends")).to_be_visible()
        expect(page.get_by_role("tab", name="LLM Costs")).to_be_visible()
        expect(page.get_by_role("tab", name="System Health")).to_be_visible()

        # Check sections
        expect(page.get_by_role("heading", name="Recruitment Funnel")).to_be_visible()

        # Check global filter
        expect(page.get_by_text("Global Filter")).to_be_visible()
        expect(page.get_by_label("Date Range")).to_be_visible()

        browser.close()
