"""
services/observability.py
Prompt 11: Structured Security & Operational Observability.

Enforces:
1. High-risk operational state logging (Prompt 11 Rule 6).
2. Credential, token, private key, and bank account number redaction/masking.
3. Safe correlation IDs (invoice_id, payment_intent_id, event_id, provider_reference, correlation_id).
4. Machine-readable structured JSON logging.
5. In-memory audit trail buffer for forensic verification and test assertions.
"""

from collections import deque
from datetime import datetime, timezone
from enum import Enum
import json
import logging
import re
import threading
from typing import Any, Dict, List, Optional, Union


# ==============================================================================
# 1. HIGH-RISK OPERATIONAL EVENT TYPES (Prompt 11 Rule 6)
# ==============================================================================

class HighRiskEvent(str, Enum):
    AMBIGUOUS_PAYMENT = "ambiguous_payment"
    DUPLICATE_SUBMISSION_SUPPRESSED = "duplicate_submission_suppressed"
    OUTBOX_RETRY = "outbox_retry"
    PROVIDER_TIMEOUT = "provider_timeout"
    CREDIT_RESERVATION_CONFLICT = "credit_reservation_conflict"
    PO_GRN_ALLOCATION_CONFLICT = "po_grn_allocation_conflict"
    INVARIANT_REJECTION = "invariant_rejection"
    WEBHOOK_AUTH_FAILURE = "webhook_auth_failure"
    SIMULATION_PRODUCTION_GATE_REJECTED = "simulation_production_gate_rejected"
    RECONCILIATION_DISCREPANCY = "reconciliation_discrepancy"
    MANUAL_OVERRIDE = "manual_override"
    HISTORICAL_REPLAY_MISMATCH = "historical_replay_mismatch"


# ==============================================================================
# 2. CREDENTIAL & PII REDACTION LOGIC
# ==============================================================================

SENSITIVE_KEY_SUBSTRINGS = (
    "password",
    "secret",
    "token",
    "private_key",
    "client_secret",
    "access_token",
    "api_key",
    "authorization",
    "webhook_secret",
    "signature_key",
    "auth_header",
    "bearer"
)

# Safe keys that should NEVER be redacted even if they contain "key"
PRESERVED_SAFE_KEYS = {
    "idempotency_key",
    "lock_key",
    "key_id",
    "key_version",
    "cache_key",
    "event_key"
}

BANK_ACCOUNT_KEYS = {
    "account_number",
    "bank_account",
    "bank_account_number",
    "source_account",
    "destination_account",
    "account_no",
    "beneficiary_account"
}

# Regex for private keys
PEM_PRIVATE_KEY_REGEX = re.compile(
    r"-----BEGIN\s+(?:[A-Z0-9_-]+\s+)?PRIVATE\s+KEY-----[\s\S]*?-----END\s+(?:[A-Z0-9_-]+\s+)?PRIVATE\s+KEY-----",
    re.IGNORECASE
)
BEARER_AUTH_REGEX = re.compile(r"Bearer\s+[A-Za-z0-9_\-\.\:\=\+\/]+", re.IGNORECASE)


def mask_bank_account(val: Any) -> str:
    """Masks bank account numbers to show only the last 4 digits (e.g. ***4321)."""
    val_str = str(val).strip()
    if len(val_str) <= 4:
        return "***" + val_str
    return f"***{val_str[-4:]}"


def sanitize_sensitive_data(val: Any) -> Any:
    """
    Recursively redacts secrets, tokens, private keys, and masks bank credentials.
    Safe against cycles and handles nested dictionaries and lists.
    """
    if isinstance(val, dict):
        sanitized = {}
        for k, v in val.items():
            k_lower = str(k).lower().strip()

            # 1. Check if safe key
            if k_lower in PRESERVED_SAFE_KEYS:
                sanitized[k] = sanitize_sensitive_data(v)
                continue

            # 2. Bank account number masking
            if k_lower in BANK_ACCOUNT_KEYS:
                sanitized[k] = mask_bank_account(v)
                continue

            # 3. Sensitive secret key redaction
            if any(sub in k_lower for sub in SENSITIVE_KEY_SUBSTRINGS):
                sanitized[k] = "[REDACTED]"
                continue

            # Recurse for nested structures
            sanitized[k] = sanitize_sensitive_data(v)
        return sanitized

    elif isinstance(val, (list, tuple)):
        return [sanitize_sensitive_data(item) for item in val]

    elif isinstance(val, str):
        # Redact raw PEM private key blocks in strings
        if "PRIVATE KEY" in val.upper():
            val = PEM_PRIVATE_KEY_REGEX.sub("[REDACTED_PRIVATE_KEY]", val)
        # Redact Bearer authorization tokens
        if "bearer" in val.lower():
            val = BEARER_AUTH_REGEX.sub("Bearer [REDACTED]", val)
        return val

    elif hasattr(val, "model_dump") and callable(getattr(val, "model_dump")):
        return sanitize_sensitive_data(val.model_dump(mode="json"))

    elif hasattr(val, "dict") and callable(getattr(val, "dict")):
        return sanitize_sensitive_data(val.dict())

    return val


# ==============================================================================
# 3. STRUCTURED JSON FORMATTER
# ==============================================================================

class JSONSecurityFormatter(logging.Formatter):
    """
    Emits single-line RFC-8259 JSON log entries with UTC ISO-8601 timestamps,
    correlation IDs, and sanitized payloads.
    """

    def format(self, record: logging.LogRecord) -> str:
        now_utc = datetime.now(timezone.utc).isoformat()
        payload = getattr(record, "structured_payload", None)

        log_dict = {
            "timestamp": now_utc,
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        if payload and isinstance(payload, dict):
            log_dict.update(payload)

        return json.dumps(log_dict, default=str)


# ==============================================================================
# 4. STRUCTURED SECURITY LOGGER (Prompt 11 Rule 6)
# ==============================================================================

class StructuredSecurityLogger:
    """
    Dedicated security and high-risk operational logger for autonomous AP operations.
    Thread-safe, supports correlation tracking and in-memory audit buffering.
    """

    def __init__(self, logger_name: str = "APSecurityAudit", max_buffer_size: int = 1000):
        self.logger = logging.getLogger(logger_name)
        self.max_buffer_size = max_buffer_size
        self._buffer: deque = deque(maxlen=max_buffer_size)
        self._lock = threading.Lock()

        # Configure JSON stream handler if not already present
        if not any(isinstance(h, logging.StreamHandler) and isinstance(h.formatter, JSONSecurityFormatter) for h in self.logger.handlers):
            handler = logging.StreamHandler()
            handler.setFormatter(JSONSecurityFormatter())
            self.logger.addHandler(handler)
            self.logger.setLevel(logging.INFO)

    def clear_buffer(self) -> None:
        """Clears the in-memory audit log buffer (useful for test isolation)."""
        with self._lock:
            self._buffer.clear()

    def get_audit_trail(self) -> List[Dict[str, Any]]:
        """Returns snapshot of recent in-memory security events."""
        with self._lock:
            return list(self._buffer)

    def log_high_risk_event(
        self,
        event_type: Union[HighRiskEvent, str],
        message: str,
        correlation: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None,
        level: str = "WARNING"
    ) -> Dict[str, Any]:
        """
        Core high-risk logging function. Guarantees structured correlation,
        credential redaction, and audit trail retention.
        """
        event_str = event_type.value if isinstance(event_type, HighRiskEvent) else str(event_type)
        now_utc = datetime.now(timezone.utc).isoformat()

        # Build clean correlation object
        raw_corr = correlation or {}
        safe_correlation = {
            "invoice_id": raw_corr.get("invoice_id"),
            "payment_intent_id": raw_corr.get("payment_intent_id") or raw_corr.get("instruction_id"),
            "event_id": raw_corr.get("event_id"),
            "provider_reference": raw_corr.get("provider_reference"),
            "correlation_id": raw_corr.get("correlation_id")
        }
        # Drop None values
        safe_correlation = {k: str(v) for k, v in safe_correlation.items() if v is not None}

        # Sanitize data payload (redact keys/tokens, mask bank accounts)
        sanitized_data = sanitize_sensitive_data(data or {})

        event_payload = {
            "timestamp": now_utc,
            "event_type": event_str,
            "level": level.upper(),
            "message": message,
            "correlation": safe_correlation,
            "data": sanitized_data
        }

        # Store in circular buffer for forensic tests
        with self._lock:
            self._buffer.append(event_payload)

        # Log via standard logging system
        lvl = getattr(logging, level.upper(), logging.WARNING)
        self.logger.log(lvl, message, extra={"structured_payload": event_payload})

        return event_payload

    # --------------------------------------------------------------------------
    # Specialized High-Risk Operational Logging Methods
    # --------------------------------------------------------------------------

    def log_ambiguous_payment(
        self,
        intent_id: str,
        provider_reference: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        return self.log_high_risk_event(
            event_type=HighRiskEvent.AMBIGUOUS_PAYMENT,
            message=f"Ambiguous or indeterminate payment outcome for intent '{intent_id}'. Reconciliation required.",
            correlation={"payment_intent_id": intent_id, "provider_reference": provider_reference, **kwargs},
            data=details,
            level="ERROR"
        )

    def log_duplicate_submission_suppressed(
        self,
        invoice_id: str,
        idempotency_key: str,
        details: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        return self.log_high_risk_event(
            event_type=HighRiskEvent.DUPLICATE_SUBMISSION_SUPPRESSED,
            message=f"Duplicate submission suppressed for invoice '{invoice_id}'. Re-execution blocked.",
            correlation={"invoice_id": invoice_id, "correlation_id": idempotency_key, **kwargs},
            data={"idempotency_key": idempotency_key, **(details or {})},
            level="WARNING"
        )

    def log_outbox_retry(
        self,
        event_id: str,
        attempt_count: int,
        max_attempts: int,
        details: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        return self.log_high_risk_event(
            event_type=HighRiskEvent.OUTBOX_RETRY,
            message=f"Outbox retry triggered for event '{event_id}' (attempt {attempt_count}/{max_attempts}).",
            correlation={"event_id": event_id, **kwargs},
            data={"attempt_count": attempt_count, "max_attempts": max_attempts, **(details or {})},
            level="WARNING"
        )

    def log_provider_timeout(
        self,
        provider: str,
        endpoint: str,
        details: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        return self.log_high_risk_event(
            event_type=HighRiskEvent.PROVIDER_TIMEOUT,
            message=f"Banking/tax provider '{provider}' timed out on endpoint '{endpoint}'.",
            correlation=kwargs,
            data={"provider": provider, "endpoint": endpoint, **(details or {})},
            level="ERROR"
        )

    def log_credit_reservation_conflict(
        self,
        credit_note_id: str,
        conflicting_invoice_id: str,
        details: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        return self.log_high_risk_event(
            event_type=HighRiskEvent.CREDIT_RESERVATION_CONFLICT,
            message=f"Credit reservation conflict on '{credit_note_id}' by invoice '{conflicting_invoice_id}'.",
            correlation={"invoice_id": conflicting_invoice_id, **kwargs},
            data={"credit_note_id": credit_note_id, **(details or {})},
            level="ERROR"
        )

    def log_po_grn_allocation_conflict(
        self,
        po_id: str,
        line_id: str,
        requested: Any,
        available: Any,
        **kwargs
    ) -> Dict[str, Any]:
        return self.log_high_risk_event(
            event_type=HighRiskEvent.PO_GRN_ALLOCATION_CONFLICT,
            message=f"PO/GRN allocation conflict on PO '{po_id}', line '{line_id}'. Requested {requested} exceeds available {available}.",
            correlation={"correlation_id": po_id, **kwargs},
            data={"po_id": po_id, "line_id": line_id, "requested": requested, "available": available},
            level="ERROR"
        )

    def log_invariant_rejection(
        self,
        invariant_name: str,
        reason: str,
        context: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        return self.log_high_risk_event(
            event_type=HighRiskEvent.INVARIANT_REJECTION,
            message=f"Financial invariant '{invariant_name}' violated: {reason}.",
            correlation=kwargs,
            data={"invariant": invariant_name, "reason": reason, **(context or {})},
            level="CRITICAL"
        )

    def log_webhook_auth_failure(
        self,
        provider: str,
        reason: str,
        remote_ip: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        return self.log_high_risk_event(
            event_type=HighRiskEvent.WEBHOOK_AUTH_FAILURE,
            message=f"Webhook authentication failed for provider '{provider}': {reason}.",
            correlation=kwargs,
            data={"provider": provider, "reason": reason, "remote_ip": remote_ip},
            level="WARNING"
        )

    def log_simulation_production_gate_rejected(
        self,
        intent_id: str,
        requested_env: str,
        reason: str,
        **kwargs
    ) -> Dict[str, Any]:
        return self.log_high_risk_event(
            event_type=HighRiskEvent.SIMULATION_PRODUCTION_GATE_REJECTED,
            message=f"Production gate rejected disbursal for intent '{intent_id}' in env '{requested_env}': {reason}.",
            correlation={"payment_intent_id": intent_id, **kwargs},
            data={"requested_environment": requested_env, "reason": reason},
            level="CRITICAL"
        )

    def log_reconciliation_discrepancy(
        self,
        record_id: str,
        expected: Any,
        actual: Any,
        details: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        return self.log_high_risk_event(
            event_type=HighRiskEvent.RECONCILIATION_DISCREPANCY,
            message=f"Reconciliation discrepancy on record '{record_id}'. Expected {expected}, got {actual}.",
            correlation={"correlation_id": record_id, **kwargs},
            data={"record_id": record_id, "expected": expected, "actual": actual, **(details or {})},
            level="WARNING"
        )

    def log_manual_override(
        self,
        actor: str,
        action: str,
        reason: str,
        approval_proof: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        return self.log_high_risk_event(
            event_type=HighRiskEvent.MANUAL_OVERRIDE,
            message=f"Manual override executed by '{actor}' for action '{action}'. Reason: {reason}.",
            correlation=kwargs,
            data={"actor": actor, "action": action, "reason": reason, "approval_proof": approval_proof},
            level="WARNING"
        )

    def log_historical_replay_mismatch(
        self,
        decision_id: str,
        original_hash: str,
        replay_hash: str,
        diff: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        return self.log_high_risk_event(
            event_type=HighRiskEvent.HISTORICAL_REPLAY_MISMATCH,
            message=f"Historical replay mismatch for decision '{decision_id}'. Original: {original_hash}, Replay: {replay_hash}.",
            correlation={"correlation_id": decision_id, **kwargs},
            data={"decision_id": decision_id, "original_hash": original_hash, "replay_hash": replay_hash, "diff": diff},
            level="CRITICAL"
        )


# Global singleton instance
_GLOBAL_SECURITY_LOGGER: Optional[StructuredSecurityLogger] = None


def get_security_logger() -> StructuredSecurityLogger:
    """Returns the process-wide StructuredSecurityLogger instance."""
    global _GLOBAL_SECURITY_LOGGER
    if _GLOBAL_SECURITY_LOGGER is None:
        _GLOBAL_SECURITY_LOGGER = StructuredSecurityLogger()
    return _GLOBAL_SECURITY_LOGGER
