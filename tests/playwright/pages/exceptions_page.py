class ExceptionsPage:
    def __init__(self, page):
        self.page = page
        self.modal = page.locator("#exception-modal")
        self.modal_title = page.locator("#exc-modal-title")
        self.radio_override = page.locator("input[name='res-action'][value='OVERRIDE']")
        self.radio_short_pay = page.locator("input[name='res-action'][value='SHORT_PAY']")
        self.radio_reject = page.locator("input[name='res-action'][value='REJECT']")
        self.note_textarea = page.locator("#exc-modal-note")
        self.btn_submit = page.locator("#btn-submit-resolution")

    def resolve_exception(self, action: str, justification: str):
        if action == "OVERRIDE":
            self.radio_override.check()
        elif action == "SHORT_PAY":
            self.radio_short_pay.check()
        elif action == "REJECT":
            self.radio_reject.check()
        self.note_textarea.fill(justification)
        self.btn_submit.click()
