from enum import Enum
import logging
from typing import Dict, Optional, Set

logger = logging.getLogger("InvoiceStateMachine")


class InvoiceState(str, Enum):
    INGESTED = "INGESTED"
    AUTO_SCHEDULED_STP = "AUTO_SCHEDULED_STP"
    AUTO_APPROVED = "AUTO_APPROVED"
    READY_TO_DISBURSE = "READY_TO_DISBURSE"
    ACTION_REQUIRED = "ACTION_REQUIRED"
    EXCEPTION_HOLD = "EXCEPTION_HOLD"
    FLAGGED_FOR_REVIEW = "FLAGGED_FOR_REVIEW"
    APPROVED_BY_CONTROLLER = "APPROVED_BY_CONTROLLER"
    SHORT_PAID_APPROVED = "SHORT_PAID_APPROVED"
    REJECTED_RETURNED_TO_VENDOR = "REJECTED_RETURNED_TO_VENDOR"
    REJECTED = "REJECTED"
    SETTLED = "SETTLED"
    PAYMENT_UNKNOWN = "PAYMENT_UNKNOWN"
    RECONCILED = "RECONCILED"


# Valid Disbursable States (WS11: Only these can be disbursed by Controller/Treasurer)
DISBURSABLE_STATES: Set[str] = {
    InvoiceState.AUTO_SCHEDULED_STP.value,
    InvoiceState.AUTO_APPROVED.value,
    InvoiceState.READY_TO_DISBURSE.value,
    InvoiceState.APPROVED_BY_CONTROLLER.value,
    InvoiceState.SHORT_PAID_APPROVED.value,
}

# Permitted State Transitions Matrix
ALLOWED_TRANSITIONS: Dict[str, Set[str]] = {
    InvoiceState.INGESTED.value: {
        InvoiceState.AUTO_SCHEDULED_STP.value,
        InvoiceState.AUTO_APPROVED.value,
        InvoiceState.ACTION_REQUIRED.value,
        InvoiceState.EXCEPTION_HOLD.value,
        InvoiceState.FLAGGED_FOR_REVIEW.value,
        InvoiceState.REJECTED.value,
    },
    InvoiceState.AUTO_SCHEDULED_STP.value: {
        InvoiceState.SETTLED.value,
        InvoiceState.PAYMENT_UNKNOWN.value,
        InvoiceState.ACTION_REQUIRED.value,
    },
    InvoiceState.AUTO_APPROVED.value: {
        InvoiceState.SETTLED.value,
        InvoiceState.PAYMENT_UNKNOWN.value,
        InvoiceState.ACTION_REQUIRED.value,
    },
    InvoiceState.READY_TO_DISBURSE.value: {
        InvoiceState.SETTLED.value,
        InvoiceState.PAYMENT_UNKNOWN.value,
        InvoiceState.ACTION_REQUIRED.value,
    },
    InvoiceState.ACTION_REQUIRED.value: {
        InvoiceState.APPROVED_BY_CONTROLLER.value,
        InvoiceState.SHORT_PAID_APPROVED.value,
        InvoiceState.REJECTED_RETURNED_TO_VENDOR.value,
        InvoiceState.REJECTED.value,
    },
    InvoiceState.EXCEPTION_HOLD.value: {
        InvoiceState.APPROVED_BY_CONTROLLER.value,
        InvoiceState.SHORT_PAID_APPROVED.value,
        InvoiceState.REJECTED_RETURNED_TO_VENDOR.value,
        InvoiceState.REJECTED.value,
    },
    InvoiceState.FLAGGED_FOR_REVIEW.value: {
        InvoiceState.APPROVED_BY_CONTROLLER.value,
        InvoiceState.SHORT_PAID_APPROVED.value,
        InvoiceState.REJECTED_RETURNED_TO_VENDOR.value,
        InvoiceState.REJECTED.value,
    },
    InvoiceState.APPROVED_BY_CONTROLLER.value: {
        InvoiceState.SETTLED.value,
        InvoiceState.PAYMENT_UNKNOWN.value,
    },
    InvoiceState.SHORT_PAID_APPROVED.value: {
        InvoiceState.SETTLED.value,
        InvoiceState.PAYMENT_UNKNOWN.value,
    },
    InvoiceState.PAYMENT_UNKNOWN.value: {
        InvoiceState.SETTLED.value,
        InvoiceState.RECONCILED.value,
        InvoiceState.ACTION_REQUIRED.value,
    },
    InvoiceState.SETTLED.value: {
        InvoiceState.RECONCILED.value,
    },
    InvoiceState.REJECTED.value: set(),
    InvoiceState.REJECTED_RETURNED_TO_VENDOR.value: set(),
    InvoiceState.RECONCILED.value: set(),
}


class InvoiceStateMachine:
    @classmethod
    def is_disbursable(cls, state: str) -> bool:
        return state in DISBURSABLE_STATES

    @classmethod
    def can_transition(cls, current: str, target: str) -> bool:
        allowed = ALLOWED_TRANSITIONS.get(current, set())
        return target in allowed

    @classmethod
    def transition(cls, current: str, target: str, strict: bool = False) -> str:
        if current == target:
            return target
        if cls.can_transition(current, target):
            logger.info(f"State machine transition: {current} -> {target}")
            return target
        
        msg = f"Invalid state machine transition requested: '{current}' -> '{target}'"
        if strict:
            logger.error(msg)
            raise ValueError(msg)
        else:
            logger.warning(f"{msg}. Permitting in non-strict mode for backwards-compatibility.")
            return target
