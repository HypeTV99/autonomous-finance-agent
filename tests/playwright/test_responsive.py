import os
import pytest
from tests.playwright.pages.dashboard_page import DashboardPage

pytestmark = pytest.mark.playwright

def ensure_screenshots_dir():
    os.makedirs("artifacts/screenshots", exist_ok=True)

def test_responsive_desktop_layout(desktop_context):
    page = desktop_context.new_page()
    dash = DashboardPage(page)
    dash.goto()

    # On desktop (1280px), table container should be visible
    page.wait_for_selector(".hidden.lg\\:block", state="visible")
    # Mobile cards container should be hidden on desktop
    assert page.eval_on_selector("#invoices-card-list", "el => window.getComputedStyle(el).display === 'none'")

    ensure_screenshots_dir()
    page.screenshot(path="artifacts/screenshots/desktop_dashboard_1280.png", full_page=False)


def test_responsive_tablet_layout(tablet_context):
    page = tablet_context.new_page()
    dash = DashboardPage(page)
    dash.goto()

    # On tablet (768px < lg), desktop table container should be hidden
    assert page.eval_on_selector(".hidden.lg\\:block", "el => window.getComputedStyle(el).display === 'none'")
    # Mobile/tablet cards should be displayed
    assert page.eval_on_selector("#invoices-card-list", "el => window.getComputedStyle(el).display !== 'none'")

    ensure_screenshots_dir()
    page.screenshot(path="artifacts/screenshots/tablet_dashboard_768.png", full_page=False)


def test_responsive_mobile_layout(mobile_context):
    page = mobile_context.new_page()
    dash = DashboardPage(page)
    dash.goto()

    # On mobile (375px < lg), desktop table container should be hidden
    assert page.eval_on_selector(".hidden.lg\\:block", "el => window.getComputedStyle(el).display === 'none'")
    # Mobile cards should be displayed
    assert page.eval_on_selector("#invoices-card-list", "el => window.getComputedStyle(el).display !== 'none'")

    ensure_screenshots_dir()
    page.screenshot(path="artifacts/screenshots/mobile_dashboard_375.png", full_page=False)


def test_all_operating_screens_visual_capture(desktop_context):
    page = desktop_context.new_page()
    dash = DashboardPage(page)
    dash.goto()
    ensure_screenshots_dir()

    # 1. Command Center
    page.screenshot(path="artifacts/screenshots/screen_1_command_center.png", full_page=False)

    # 2. Ingestion
    page.locator("#nav-btn-ingestion").click()
    page.wait_for_timeout(300)
    page.screenshot(path="artifacts/screenshots/screen_2_ingestion.png", full_page=False)

    # 3. AP Workspace
    page.locator("#nav-btn-workspace").click()
    page.wait_for_timeout(300)
    page.screenshot(path="artifacts/screenshots/screen_3_workspace.png", full_page=False)

    # 4. Detail Modal
    page.evaluate("openFullDetailModal('INV-884')")
    page.wait_for_timeout(300)
    page.screenshot(path="artifacts/screenshots/screen_3_detail_modal.png", full_page=False)
    page.keyboard.press("Escape")
    page.wait_for_timeout(200)

    # 5. Exceptions
    page.locator("#nav-btn-exceptions").click()
    page.wait_for_timeout(300)
    page.screenshot(path="artifacts/screenshots/screen_4_exceptions.png", full_page=False)

    # 6. Treasury
    page.locator("#nav-btn-treasury").click()
    page.wait_for_timeout(300)
    page.screenshot(path="artifacts/screenshots/screen_5_treasury.png", full_page=False)

    # 7. Auditor
    page.locator("#nav-btn-auditor").click()
    page.wait_for_timeout(300)
    page.screenshot(path="artifacts/screenshots/screen_6_auditor.png", full_page=False)

