class DashboardPage:
    def __init__(self, page):
        self.page = page
        self.skip_link = page.locator("a[href='#main-content']")
        self.env_badge = page.locator("text=SANDBOX / UAT SIMULATION")
        self.role_select = page.locator("#user-role-select")
        self.search_input = page.locator("#universal-search")
        self.kpi_settled = page.locator("#metric-hero-settled")
        self.kpi_tds = page.locator("#metric-hero-tds")
        self.kpi_escrow = page.locator("#metric-hero-escrow")
        self.kpi_liquidity = page.locator("#metric-hero-liquidity")
        self.waterfall_variance = page.locator("#waterfall-variance-badge")
        self.desktop_table = page.locator(".hidden.lg\\:block table")
        self.mobile_card_list = page.locator("#invoices-card-list")
        self.btn_batch_disburse = page.locator("#btn-open-batch-disburse")
        self.btn_batch_label = page.locator("#btn-batch-disburse-label")

    def goto(self):
        self.page.goto("/dashboard")
        self.page.wait_for_load_state("domcontentloaded")

    def switch_role(self, role_value: str):
        self.role_select.select_option(role_value)

    def filter_tab(self, tab_id: str):
        self.page.locator(f"#qtab-{tab_id.lower()}").click()

    def search_invoice(self, query: str):
        self.search_input.fill(query)
