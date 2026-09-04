class AuditPage:
    def __init__(self, page):
        self.page = page
        self.title = page.locator("text=Audit & Evidence")
        self.search_input = page.locator("#audit-search")
        self.invoice_select = page.locator("#invoice-select")
        self.tab_exec = page.locator("#tab-btn-exec")
        self.tab_forensic = page.locator("#tab-btn-forensic")
        self.panel_exec = page.locator("#tab-content-executive")
        self.panel_forensic = page.locator("#tab-content-forensic")
        self.card_controls = page.locator("#card-controls-val")
        self.card_journal = page.locator("#card-journal-val")
        self.card_payment = page.locator("#card-payment-val")
        self.card_evidence = page.locator("#card-evidence-val")
        self.audit_table = page.locator("#audit-table")
        self.audit_card_list = page.locator("#audit-card-list")
        self.drawer = page.locator("#audit-detail-drawer")
        self.drawer_close_btn = page.locator("#drawer-close-btn")
        self.acc_source = page.locator("#acc-source-integrity")
        self.acc_controls = page.locator("#acc-control-evaluations")
        self.acc_approvals = page.locator("#acc-approvals-settlement")
        self.acc_signature = page.locator("#acc-signature-verification")

    def goto(self):
        self.page.goto("/audit")
        self.page.wait_for_load_state("domcontentloaded")

    def switch_tab(self, tab_name: str):
        if tab_name.upper() == "EXECUTIVE":
            self.tab_exec.click()
        else:
            self.tab_forensic.click()

    def open_drawer_for_first_row(self):
        btn = self.page.locator("#audit-tbody button:has-text('Review')").first
        btn.click()

    def close_drawer(self):
        self.drawer_close_btn.click()
