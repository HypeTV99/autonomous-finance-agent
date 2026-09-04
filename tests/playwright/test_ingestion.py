import pytest
from tests.playwright.pages.dashboard_page import DashboardPage

pytestmark = pytest.mark.playwright

def test_document_ingestion_trigger(desktop_context):
    """
    Asserts document ingestion controls and upload triggers.
    """
    page = desktop_context.new_page()
    dash = DashboardPage(page)
    dash.goto()

    # Verify global file input exists for drag-and-drop or click ingestion
    file_input = page.locator("#global-file-input")
    assert file_input.count() == 1
    assert file_input.get_attribute("type") == "file"
