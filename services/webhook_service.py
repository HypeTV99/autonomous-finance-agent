import hashlib
import hmac
import json
import logging
import time
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, Optional, Tuple

from firestore_store import FirestoreStateStore
from schemas import PaymentState, WebhookEventRecord
from services.observability import get_security_logger

logger = logging.getLogger("ProviderWebhookService")
security_logger = get_security_logger()


class WebhookAuthenticationError(Exception):
    """Raised when webhook signature verification fails."""
    pass


class WebhookReplayError(Exception):
    """Raised when webhook timestamp falls outside replay protection tolerance."""
    pass


class ProviderWebhookService:
    """
    Hardened Asynchronous Provider Webhook Service (RazorpayX / Banking Rail).
    Implements:
    1. Cryptographic HMAC-SHA256 signature verification in constant time.
    2. Replay window protection (tolerance: default +- 300 seconds).
    3. Persistence-level event deduplication by provider event_id.
    4. Out-of-order callback protection (never regresses terminal states like SETTLED).
    5. Synchronous gateway response / webhook callback race condition convergence.
    6. High-risk action fencing (reversals require explicit Controller approval; no autonomous ledger mutation).
    """

    REPLAY_TOLERANCE_SECONDS = 300.0  # 5-minute replay window

    def __init__(self, store: Optional[FirestoreStateStore] = None):
        self.store = store or FirestoreStateStore()

    @classmethod
    def verify_signature(cls, raw_body: bytes, signature: str, secret: str) -> bool:
        """Verifies provider webhook HMAC-SHA256 signature using constant-time comparison."""
        if not signature or not secret:
            return False
        expected_sig = hmac.new(
            key=secret.encode("utf-8") if isinstance(secret, str) else secret,
            msg=raw_body,
            digestmod=hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(expected_sig.strip(), signature.strip())

    def process_razorpayx_webhook(
        self,
        raw_body: bytes,
        signature: str,
        secret: str,
        current_time_epoch: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Authoritatively parses, authenticates, deduplicates, and converges a RazorpayX webhook event.
        """
        now_ts = current_time_epoch if current_time_epoch is not None else time.time()
        now_iso = datetime.now(timezone.utc).isoformat()
        payload_sha256 = hashlib.sha256(raw_body).hexdigest()

        # 1. Cryptographic Signature Verification
        if not self.verify_signature(raw_body, signature, secret):
            logger.warning("Webhook rejected: Invalid HMAC-SHA256 signature.")
            security_logger.log_webhook_auth_failure(
                provider="RAZORPAYX",
                reason="Invalid HMAC-SHA256 signature",
                remote_ip=None
            )
            raise WebhookAuthenticationError("Invalid webhook signature")

        # 2. Parse JSON Payload
        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except Exception as e:
            logger.error(f"Failed to parse webhook JSON payload: {e}")
            raise ValueError(f"Malformed JSON payload: {e}")

        # 3. Replay Window Protection
        event_created_at = payload.get("created_at")
        if event_created_at is not None:
            try:
                created_ts = float(event_created_at)
                # If timestamp in milliseconds
                if created_ts > 1e11:
                    created_ts /= 1000.0
                time_skew = abs(now_ts - created_ts)
                if time_skew > self.REPLAY_TOLERANCE_SECONDS:
                    logger.warning(f"Webhook rejected: Timestamp skew {time_skew:.1f}s exceeds tolerance {self.REPLAY_TOLERANCE_SECONDS}s.")
                    security_logger.log_webhook_auth_failure(
                        provider="RAZORPAYX",
                        reason=f"Timestamp skew {time_skew:.1f}s exceeds tolerance {self.REPLAY_TOLERANCE_SECONDS}s"
                    )
                    raise WebhookReplayError(
                        f"Webhook timestamp skew ({time_skew:.1f}s) exceeds replay window tolerance ({self.REPLAY_TOLERANCE_SECONDS}s)"
                    )
            except (ValueError, TypeError):
                pass

        # 4. Extract Event Metadata
        event_type = str(payload.get("event", "unknown"))
        event_id = str(
            payload.get("event_id") or payload.get("id") or f"evt_{payload_sha256[:16]}"
        ).strip()

        payout_entity = (
            payload.get("payload", {}).get("payout", {}).get("entity", {})
            if isinstance(payload.get("payload"), dict)
            else {}
        )
        notes = payout_entity.get("notes", {}) if isinstance(payout_entity, dict) else {}
        idempotency_key = (
            notes.get("idempotency_key") or
            payout_entity.get("reference_id") or
            payload.get("idempotency_key")
        )
        utr = payout_entity.get("utr")
        payout_id = payout_entity.get("id")

        # 5. Persistence-Level Event Deduplication
        event_record = {
            "event_id": event_id,
            "provider": "RAZORPAYX",
            "event_type": event_type,
            "raw_payload_sha256": payload_sha256,
            "signature_verified": True,
            "processing_status": "PROCESSING",
            "received_at": now_iso,
            "idempotency_key": idempotency_key
        }
        is_new_event = self.store.save_webhook_event(event_record)
        if not is_new_event:
            logger.info(f"Webhook event '{event_id}' already processed. Idempotently returning acknowledgment.")
            return {
                "status": "DUPLICATE_IGNORED",
                "event_id": event_id,
                "message": "Duplicate event acknowledged idempotently without side-effects."
            }

        # 6. Process Specific Event Types with State Machine & Terminal Protection
        if not idempotency_key:
            return {"status": "ACKNOWLEDGED", "event_id": event_id}

        existing_intent = self.store.get_payment_intent(idempotency_key)
        if not existing_intent:
            logger.warning(f"Webhook received for unknown payment intent '{idempotency_key}'.")
            return {"status": "ACKNOWLEDGED_UNKNOWN_INTENT", "event_id": event_id}

        current_state = existing_intent.get("status", PaymentState.CREATED.value)

        # 7. High-Risk Action Fencing: Payout Reversal
        if event_type == "payout.reversed":
            logger.critical(
                f"HIGH-RISK EVENT: Payout reversal received for intent '{idempotency_key}' (Payout: {payout_id}). "
                f"Autonomous general ledger reversal is strictly fenced behind explicit Controller approval."
            )
            # Update payment intent with reversal pending review flag
            self.store.update_payment_intent(
                idempotency_key=idempotency_key,
                update_dict={
                    "reversal_pending_approval": True,
                    "reversal_event_id": event_id,
                    "reversal_received_at": now_iso,
                    "reversal_payout_id": payout_id,
                    "reversal_reason": payout_entity.get("failure_reason") or "Provider initiated payout reversal"
                }
            )
            self.store.record_state_transition({
                "idempotency_key": idempotency_key,
                "from_state": current_state,
                "to_state": current_state,
                "resulting_version": existing_intent.get("version", 1),
                "actor_id": f"WEBHOOK_RAZORPAYX_{event_id}",
                "actor_type": "WEBHOOK",
                "reason_code": "REVERSAL_FLAGGED_FOR_APPROVAL",
                "reason_text": "Payout reversal received. Autonomous ledger mutation blocked; flagged for manual Controller approval.",
                "timestamp": now_iso
            })
            return {
                "status": "REVERSAL_PENDING_APPROVAL",
                "event_id": event_id,
                "idempotency_key": idempotency_key,
                "requires_manual_approval": True,
                "message": "Payout reversal flagged for explicit manual Controller approval. No autonomous accounting reversal executed."
            }

        # 8. Terminal State Protection (Out-of-Order Callbacks)
        if current_state in (PaymentState.SETTLED.value, PaymentState.RECONCILED.value):
            if event_type in ("payout.initiated", "payout.pending", "payout.queued"):
                logger.info(
                    f"Out-of-order webhook event '{event_type}' arrived after intent '{idempotency_key}' "
                    f"is already {current_state}. Preserving terminal state."
                )
                self.store.record_state_transition({
                    "idempotency_key": idempotency_key,
                    "from_state": current_state,
                    "to_state": current_state,
                    "resulting_version": existing_intent.get("version", 1),
                    "actor_id": f"WEBHOOK_RAZORPAYX_{event_id}",
                    "actor_type": "WEBHOOK",
                    "reason_code": "OUT_OF_ORDER_IGNORED",
                    "reason_text": f"Out-of-order callback '{event_type}' ignored because intent is already terminal ({current_state}).",
                    "timestamp": now_iso
                })
                return {
                    "status": "CONVERGED_TERMINAL",
                    "event_id": event_id,
                    "current_state": current_state,
                    "message": f"State {current_state} preserved against out-of-order event {event_type}."
                }

        # 9. Settlement Convergence
        if event_type in ("payout.processed", "payout.settled"):
            new_utr = utr or existing_intent.get("utr") or f"RZX{payout_id or event_id[:8]}"
            self.store.update_payment_intent(
                idempotency_key=idempotency_key,
                update_dict={
                    "status": PaymentState.SETTLED.value,
                    "provider_reference": payout_id or existing_intent.get("provider_reference"),
                    "utr": new_utr,
                    "settled_at": now_iso
                }
            )
            self.store.record_state_transition({
                "idempotency_key": idempotency_key,
                "from_state": current_state,
                "to_state": PaymentState.SETTLED.value,
                "resulting_version": existing_intent.get("version", 1) + 1,
                "actor_id": f"WEBHOOK_RAZORPAYX_{event_id}",
                "actor_type": "WEBHOOK",
                "reason_code": "PAYOUT_PROCESSED_WEBHOOK",
                "reason_text": f"Settled via provider callback. UTR: {new_utr}",
                "timestamp": now_iso
            })
            return {
                "status": "SETTLED",
                "event_id": event_id,
                "idempotency_key": idempotency_key,
                "utr": new_utr
            }

        # 10. Failure Handling
        if event_type == "payout.failed":
            if current_state != PaymentState.SETTLED.value:
                self.store.update_payment_intent(
                    idempotency_key=idempotency_key,
                    update_dict={
                        "status": PaymentState.FAILED.value,
                        "last_error": payout_entity.get("failure_reason") or "Payout failed at bank rail"
                    }
                )
                self.store.record_state_transition({
                    "idempotency_key": idempotency_key,
                    "from_state": current_state,
                    "to_state": PaymentState.FAILED.value,
                    "resulting_version": existing_intent.get("version", 1) + 1,
                    "actor_id": f"WEBHOOK_RAZORPAYX_{event_id}",
                    "actor_type": "WEBHOOK",
                    "reason_code": "PAYOUT_FAILED_WEBHOOK",
                    "reason_text": f"Provider failed callback: {payout_entity.get('failure_reason')}",
                    "timestamp": now_iso
                })
            return {
                "status": "FAILED",
                "event_id": event_id,
                "idempotency_key": idempotency_key
            }

        return {"status": "ACKNOWLEDGED", "event_id": event_id}
