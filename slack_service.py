import base64
import hashlib
import hmac
import json
import logging
import time
from typing import Tuple
import requests
from schemas import ApprovalTier

logger = logging.getLogger("SlackService")


class HardenedSlackService:
    def __init__(self, webhook_url: str, signing_secret: str):
        self.webhook_url = webhook_url
        self.signing_secret = signing_secret.encode("utf-8")

    def generate_action_token(self, invoice_number: str, action: str, valid_for_seconds: int = 86400) -> str:
        expires_at = int(time.time()) + valid_for_seconds
        payload_raw = f"{invoice_number}:{action}:{expires_at}"
        signature = hmac.new(self.signing_secret, payload_raw.encode("utf-8"), hashlib.sha256).hexdigest()
        token_data = {"inv": invoice_number, "act": action, "exp": expires_at, "sig": signature}
        return base64.urlsafe_b64encode(json.dumps(token_data).encode("utf-8")).decode("utf-8")

    def verify_action_token(self, token: str) -> Tuple[bool, str, str]:
        try:
            raw_bytes = base64.urlsafe_b64decode(token.encode("utf-8"))
            data = json.loads(raw_bytes.decode("utf-8"))
            inv, act, exp, sig = data["inv"], data["act"], data["exp"], data["sig"]

            expected_raw = f"{inv}:{act}:{exp}"
            expected_sig = hmac.new(self.signing_secret, expected_raw.encode("utf-8"), hashlib.sha256).hexdigest()
            if not hmac.compare_digest(sig, expected_sig):
                return False, "", "FORGED"

            if int(time.time()) > exp:
                return False, "", "EXPIRED"

            return True, inv, act
        except Exception:
            return False, "", "CORRUPTED"

    def dispatch_tiered_alert(
        self,
        tier: ApprovalTier,
        invoice_number: str,
        vendor_name: str,
        amount_inr: str,
        reason: str,
        details: str
    ) -> bool:
        approve_token = self.generate_action_token(invoice_number, "APPROVE")
        reject_token = self.generate_action_token(invoice_number, "REJECT")

        blocks = [
            {"type": "header", "text": {"type": "plain_text", "text": f"⚠️ AP Exception: {tier.value} Authorization Required", "emoji": True}},
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Invoice:* `{invoice_number}`"},
                    {"type": "mrkdwn", "text": f"*Vendor:* {vendor_name}"},
                    {"type": "mrkdwn", "text": f"*Amount:* ₹{amount_inr}"},
                    {"type": "mrkdwn", "text": f"*Reason:* `{reason}`"}
                ]
            },
            {"type": "section", "text": {"type": "mrkdwn", "text": f"*Discrepancy Details:* {details}"}},
            {
                "type": "actions",
                "elements": [
                    {"type": "button", "text": {"type": "plain_text", "text": "Approve & Stage"}, "style": "primary", "value": approve_token, "action_id": "approve_action"},
                    {"type": "button", "text": {"type": "plain_text", "text": "Reject Bill"}, "style": "danger", "value": reject_token, "action_id": "reject_action"}
                ]
            }
        ]
        try:
            if "MOCK" in self.webhook_url or "test" in self.webhook_url:
                logger.info(f"Mock Slack Block Kit Dispatched: Invoice={invoice_number}, Reason={reason}")
                return True
            res = requests.post(self.webhook_url, json={"blocks": blocks}, timeout=5.0)
            return res.status_code == 200
        except Exception as e:
            logger.error(f"Slack delivery error: {e}")
            return False
