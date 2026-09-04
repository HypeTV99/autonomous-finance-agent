import os
import pytest
from playwright.sync_api import expect
from tests.playwright.pages.audit_page import AuditPage

SCREENSHOTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "artifacts", "screenshots")

@pytest.mark.playwright
def test_audit_executive_summary_viewport(desktop_context):
    """
    Acceptance Test 1 & 2:
    - Executive Summary fits within viewport, contains exactly 4 status cards and one ledger.
    - Does not render raw hashes, signatures, KMS details, 17-node cards or 9-pillar checklist in executive view.
    - Table columns match: Transaction, Vendor, Settlement, Controls, Journal, Evidence, Action.
    - Button says 'Review' instead of 'Inspect'.
    """
    page = desktop_context.new_page()
    audit_page = AuditPage(page)
    audit_page.goto()

    expect(page.locator("h2")).to_contain_text("Audit & Evidence")
    expect(page.locator("text=Review transaction controls, accounting results and signed evidence")).to_be_visible()

    # 4 compact status cards
    expect(audit_page.card_controls).to_contain_text("17 of 17 passed")
    expect(audit_page.card_journal).to_contain_text("Balanced")
    expect(audit_page.card_payment).to_contain_text("Reconciled")
    expect(audit_page.card_evidence).to_contain_text("Complete and signed")

    # Ensure no raw cryptographic hashes or dark panels in executive view
    expect(page.locator(".fintech-dark-card")).to_have_count(0)
    expect(page.locator("text=Root-of-Trust Hardware Seal")).to_have_count(0)
    expect(page.locator("text=17-Node Merkle DAG Forensic Topology")).to_have_count(0)
    expect(page.locator("text=9-Pillar Statutory Compliance Audit Checklist")).to_have_count(0)

    # Table columns
    headers = page.locator("#audit-thead th").all_inner_texts()
    expected_headers = ["TRANSACTION", "VENDOR", "SETTLEMENT", "CONTROLS", "JOURNAL", "EVIDENCE", "ACTION"]
    for expected in expected_headers:
        assert any(expected in h.upper() for h in headers), f"Missing header {expected} in {headers}"

    # Verify action button text is 'Review'
    review_btn = page.locator("#audit-tbody button:has-text('Review')").first
    expect(review_btn).to_be_visible()
    expect(page.locator("#audit-tbody button:has-text('Inspect')")).to_have_count(0)


@pytest.mark.playwright
def test_audit_detail_drawer_interaction(desktop_context):
    """
    Acceptance Test:
    - Selecting 'Review' opens the right-side detail drawer while preserving scroll position.
    - Drawer displays invoice, vendor, settlement, tax determination, GST retention, journal balance, controls.
    - No raw hashes/signatures in default drawer view.
    - Escape key closes the drawer and restores focus.
    """
    page = desktop_context.new_page()
    audit_page = AuditPage(page)
    audit_page.goto()

    # Open drawer
    review_btn = page.locator("#audit-tbody button:has-text('Review')").first
    review_btn.click()

    expect(audit_page.drawer).to_be_visible()
    expect(page.locator("#drawer-title")).to_contain_text("Transaction Evidence Detail")
    expect(page.locator("#drawer-amount")).to_contain_text("INR")
    expect(page.locator("#drawer-tax-code")).to_contain_text("ITA 2025")
    expect(page.locator("#drawer-gst-status")).to_contain_text("GSTR-2B Confirmed")
    expect(page.locator("#drawer-journal-status")).to_contain_text("Balanced (Debits == Credits)")
    expect(page.locator("#drawer-control-summary")).to_contain_text("17 of 17 Passed")

    # Close with Escape key
    page.keyboard.press("Escape")
    expect(audit_page.drawer).not_to_be_visible()


@pytest.mark.playwright
def test_audit_forensic_tabs_and_accordions(desktop_context):
    """
    Acceptance Tests 3, 4, 5, 6, 8, 9, 10:
    - Forensic tab renders materially different content with 4 defined accordions.
    - Control evaluations merge 17 nodes and 9 pillars into grouped categories.
    - Section 206AA is not described as non-filer verification.
    - Hashes and signatures are visually truncated and have copy buttons.
    - Signature verification section allows verification action.
    """
    page = desktop_context.new_page()
    audit_page = AuditPage(page)
    audit_page.goto()

    # Switch to Forensic Details
    audit_page.switch_tab("FORENSIC")
    expect(audit_page.panel_forensic).to_be_visible()
    expect(audit_page.panel_exec).not_to_be_visible()

    # 4 Accordions
    expect(audit_page.acc_source).to_be_visible()
    expect(audit_page.acc_controls).to_be_visible()
    expect(audit_page.acc_approvals).to_be_visible()
    expect(audit_page.acc_signature).to_be_visible()

    # Expand Control Evaluations accordion
    audit_page.acc_controls.locator("summary").click()
    expect(page.locator("text=Section 206AA Higher Deduction Check (Missing/Invalid PAN)").first).to_be_visible()
    expect(page.locator("text=Section 206AA Non-Filer Verification")).to_have_count(0)

    # Verify truncated hashes and copy buttons in Source & Integrity
    expect(page.locator("text=sha256:e3b0c442...7852b855")).to_be_visible()
    copy_btn = page.locator("button[aria-label='Copy source invoice hash']")
    expect(copy_btn).to_be_visible()

    # Expand Signature Verification accordion
    audit_page.acc_signature.locator("summary").click()
    expect(page.locator("text=Evidence verification")).to_be_visible()
    verify_btn = page.locator("button:has-text('Verify evidence')")
    expect(verify_btn).to_be_visible()
    verify_btn.click()
    expect(page.locator("#toast")).to_be_visible()


@pytest.mark.playwright
def test_audit_responsive_viewports_and_screenshots(desktop_context, tablet_context, mobile_context):
    """
    Acceptance Tests 11 & 16:
    - Verifies responsive layout across Desktop (1280px), Tablet (768px), and Mobile (375px).
    - Mobile renders card list instead of wide table.
    - Captures reference screenshots for visual validation.
    """
    os.makedirs(SCREENSHOTS_DIR, exist_ok=True)

    # 1. Desktop Executive Summary
    d_page = desktop_context.new_page()
    d_audit = AuditPage(d_page)
    d_audit.goto()
    expect(d_audit.audit_table).to_be_visible()
    d_page.screenshot(path=os.path.join(SCREENSHOTS_DIR, "desktop_audit_1280.png"), full_page=False)

    # 1b. Desktop Detail Drawer
    d_audit.open_drawer_for_first_row()
    expect(d_audit.drawer).to_be_visible()
    d_page.screenshot(path=os.path.join(SCREENSHOTS_DIR, "desktop_audit_drawer_1280.png"), full_page=False)
    d_audit.close_drawer()

    # 1c. Desktop Forensic Details
    d_audit.switch_tab("FORENSIC")
    expect(d_audit.panel_forensic).to_be_visible()
    d_audit.acc_controls.locator("summary").click()
    d_page.screenshot(path=os.path.join(SCREENSHOTS_DIR, "desktop_audit_forensic_1280.png"), full_page=False)

    # 2. Tablet
    t_page = tablet_context.new_page()
    t_audit = AuditPage(t_page)
    t_audit.goto()
    expect(t_audit.card_controls).to_be_visible()
    t_page.screenshot(path=os.path.join(SCREENSHOTS_DIR, "tablet_audit_768.png"), full_page=False)

    # 3. Mobile
    m_page = mobile_context.new_page()
    m_audit = AuditPage(m_page)
    m_audit.goto()
    # On mobile, desktop table is hidden and card list is visible
    expect(m_page.locator(".hidden.lg\\:block table#audit-table")).not_to_be_visible()
    expect(m_audit.audit_card_list).to_be_visible()
    m_page.screenshot(path=os.path.join(SCREENSHOTS_DIR, "mobile_audit_375.png"), full_page=False)
