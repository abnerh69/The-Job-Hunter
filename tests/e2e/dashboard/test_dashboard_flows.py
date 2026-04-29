import pytest
import time
import os
import subprocess
from playwright.sync_api import Page, expect

@pytest.fixture(scope="module", autouse=True)
def streamlit_server():
    # Setup environment
    env = os.environ.copy()
    env["ANTHROPIC_API_KEY"] = "dummy"
    env["DASHBOARD_PASSWORD"] = "secret123"
    env["PYTHONPATH"] = "src"

    # Run streamlit
    cmd = ["uv", "run", "streamlit", "run", "src/jobhunter/dashboard/streamlit_app.py", "--server.port=8501", "--server.headless=true"]
    process = subprocess.Popen(cmd, env=env)

    # Wait for server to start
    time.sleep(5)

    yield

    # Kill server
    process.terminate()
    process.wait()

def test_login_flow(page: Page):
    page.goto("http://localhost:8501")

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

def test_page_protection(page: Page):
    # Try to access a page directly
    # Note: Streamlit pages URLs are usually /Page_Name
    page.goto("http://localhost:8501/New_Matches")
    time.sleep(2)

    # Should be redirected or shown login
    expect(page.get_by_role("textbox", name="Password")).to_be_visible()

def test_logout(page: Page):
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
