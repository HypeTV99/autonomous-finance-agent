class TreasuryPage:
    def __init__(self, page):
        self.page = page
        self.batch_modal = page.locator("#batch-disburse-confirm-modal")
        self.batch_count = page.locator("#batch-modal-count")
        self.batch_gross = page.locator("#batch-modal-gross")
        self.batch_tds = page.locator("#batch-modal-tds")
        self.batch_net = page.locator("#batch-modal-net")
        self.btn_confirm_payout = page.locator("#btn-confirm-batch-payout")

    def open_batch_disburse(self):
        self.page.locator("#btn-open-batch-disburse").click()

    def confirm_batch_payout(self):
        self.btn_confirm_payout.click()
