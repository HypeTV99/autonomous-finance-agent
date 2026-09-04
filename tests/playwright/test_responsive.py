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
