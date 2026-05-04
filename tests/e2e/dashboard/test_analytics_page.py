import pytest
import time
from playwright.sync_api import Page, expect


@pytest.mark.e2e
def test_analytics_page_recommendations(page: Page, live_server_url: str) -> None:
    # Setup: Login
    page.goto(live_server_url)
    password_field = page.get_by_label("Password").first
    if password_field.is_visible():
        password_field.fill("secret123")  # pragma: allowlist secret
        password_field.press("Enter")
        time.sleep(2)

    page.goto(f"{live_server_url}/Analytics")

    # Wait for recommendations section
    expect(page.get_by_text("Actionable Recommendations")).to_be_visible()

    # Check if any recommendation card exists
    reco_cards = page.locator("div[data-testid='stVerticalBlockBorderWrapper']")
    if reco_cards.count() > 0:
        first_reco = reco_cards.first

        # Click Snooze on the first one
        snooze_btn = first_reco.get_by_role("button", name="Snooze (7d)")
        if snooze_btn.is_visible():
            snooze_btn.click()
            page.wait_for_timeout(1000)
    else:
        print("No recommendations found to test interaction.")


@pytest.mark.e2e
def test_analytics_page_sections(page: Page, live_server_url: str) -> None:
    # Setup: Login
    page.goto(live_server_url)
    password_field = page.get_by_label("Password").first
    if password_field.is_visible():
        password_field.fill("secret123")  # pragma: allowlist secret
        password_field.press("Enter")
        time.sleep(2)

    page.goto(f"{live_server_url}/Analytics")

    expect(page.get_by_text("Active A/B Tests")).to_be_visible()
    expect(page.get_by_text("False Rejects Review")).to_be_visible()
    expect(page.get_by_text("Reports Archive")).to_be_visible()
    expect(page.get_by_role("button", name="Generate Monthly Report")).to_be_visible()
