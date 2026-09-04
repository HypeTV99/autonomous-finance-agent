class InvoicePage:
    def __init__(self, page):
        self.page = page
        self.file_input = page.locator("#global-file-input")
        self.toast = page.locator("#toast")
        self.toast_msg = page.locator("#toast-msg")

    def upload_invoice(self, file_path: str):
        self.file_input.set_input_files(file_path)

    def get_toast_text(self):
        self.toast.wait_for(state="visible", timeout=5000)
        return self.toast_msg.inner_text()
