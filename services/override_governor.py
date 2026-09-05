from datetime import datetime, timezone
from decimal import Decimal
import logging
from typing import Any, Dict, Optional

from schemas import ManualOverrideRecord, OverrideScope
from services.observability import get_security_logger

logger = logging.getLogger("OverrideGovernor")


class OverrideGovernorError(Exception):
    """Base exception for manual override governance."""
    pass


class MakerCheckerViolationError(OverrideGovernorError):
    """Raised when dual-control maker-checker segregation is violated (e.g. maker == checker)."""
    pass


class OverrideExpiredError(OverrideGovernorError):
    """Raised when an override has expired."""
    pass


class InsufficientOverrideScopeError(OverrideGovernorError):
    """Raised when an override scope does not authorize the target operation."""
    pass


class NonOverridableInvariantViolationError(OverrideGovernorError):
    """Raised when an override attempts to breach a non-overridable core invariant."""
    pass


class OverrideGovernor:
    """
    Authoritative Governance Engine for Manual Overrides.
    Enforces:
    1. Maker-Checker Segregation of Duties (maker != checker).
    2. Explicit Scope Authorization and Active Expiry Windows.
    3. Strict Non-Overridable Invariant Fencing:
       - No duplicate economic payments
       - No credit over-consumption (consumed > original / available)
       - No unbalanced general ledger journals (Debits != Credits)
       - No historical evidence / signed decision mutation
       - No simulation data masquerading as live disbursals
       - No procurement quantity expansion without formal PO revision
    """

    @classmethod
    def validate_override(
        cls,
        override: ManualOverrideRecord,
        required_scope: OverrideScope,
        current_time: Optional[datetime] = None
    ) -> None:
        """
        Validates override dual-control, scope matching, and active expiry window.
        """
        if not override:
            raise OverrideGovernorError("No override record provided.")

        # 1. Maker-Checker Segregation of Duties
        try:
            override.validate_maker_checker()
        except ValueError as ve:
            raise MakerCheckerViolationError(str(ve)) from ve

        # 2. Inactive / Revoked Check
        if not override.is_active:
            raise OverrideGovernorError(f"Override '{override.override_id}' is marked inactive or revoked.")

        # 3. Expiry Check
        if override.is_expired(current_time):
            raise OverrideExpiredError(
                f"Override '{override.override_id}' expired at '{override.expiry}'. Current time: {current_time or datetime.now(timezone.utc)}"
            )

        # 4. Scope Check
        if override.scope != required_scope and override.scope != OverrideScope.GENERAL_POLICY:
            raise InsufficientOverrideScopeError(
                f"Override '{override.override_id}' has scope '{override.scope.value}', "
                f"which does not grant required authority for '{required_scope.value}'."
            )

        # Log authorized manual override
        get_security_logger().log_manual_override(
            actor=override.checker_id,
            action=override.scope.value,
            reason=override.justification,
            approval_proof={
                "override_id": override.override_id,
                "maker_id": override.maker_id,
                "checker_id": override.checker_id,
                "scope": override.scope.value,
                "expiry": override.expiry
            }
        )

    @classmethod
    def assert_can_override_duplicate_payment(
        cls,
        override: ManualOverrideRecord,
        is_economic_duplicate: bool
    ) -> None:
        """
        Fences duplicate economic payments. Even with a CFO override, paying an identical
        economic obligation twice is strictly illegal.
        """
        if is_economic_duplicate:
            get_security_logger().log_invariant_rejection(
                invariant_name="NO_DUPLICATE_ECONOMIC_PAYMENT",
                reason="Attempted to authorize duplicate payment with override",
                context={"override_id": override.override_id}
            )
            raise NonOverridableInvariantViolationError(
                "NON-OVERRIDABLE INVARIANT: Duplicate economic payment cannot be authorized by manual override. "
                "The duplicate invoice must be cleared via credit note, cancellation, or formal dispute."
            )

    @classmethod
    def assert_can_override_credit_limit(
        cls,
        override: ManualOverrideRecord,
        consumed_amount: Decimal,
        available_amount: Decimal
    ) -> None:
        """
        Fences credit conservation. Consumed credit cannot exceed available/original credit.
        """
        if consumed_amount > available_amount:
            get_security_logger().log_invariant_rejection(
                invariant_name="CREDIT_CONSERVATION",
                reason=f"Consumed ₹{consumed_amount} exceeds available ₹{available_amount}",
                context={"override_id": override.override_id}
            )
            raise NonOverridableInvariantViolationError(
                f"NON-OVERRIDABLE INVARIANT: Credit over-consumption cannot be authorized by manual override. "
                f"Attempted to consume ₹{consumed_amount}, but only ₹{available_amount} is available."
            )

    @classmethod
    def assert_can_override_unbalanced_journal(
        cls,
        override: ManualOverrideRecord,
        total_debits: Decimal,
        total_credits: Decimal
    ) -> None:
        """
        Fences double-entry balance. Under Ind AS 1 / IFRS, debits must strictly equal credits.
        """
        if total_debits != total_credits:
            get_security_logger().log_invariant_rejection(
                invariant_name="DOUBLE_ENTRY_BALANCE",
                reason=f"Debits ₹{total_debits} != Credits ₹{total_credits}",
                context={"override_id": override.override_id}
            )
            raise NonOverridableInvariantViolationError(
                f"NON-OVERRIDABLE INVARIANT: Unbalanced general ledger journal cannot be authorized by manual override. "
                f"Total Debits (₹{total_debits}) != Total Credits (₹{total_credits})."
            )

    @classmethod
    def assert_can_override_historical_mutation(
        cls,
        override: ManualOverrideRecord
    ) -> None:
        """
        Fences historical immutable decision ledger. Mutations must use reversal + replacement lineage.
        """
        raise NonOverridableInvariantViolationError(
            "NON-OVERRIDABLE INVARIANT: Historical decision attestation and signed evidence cannot be mutated or overwritten. "
            "Adjustments must be posted as a reversal entry referencing the original lineage."
        )

    @classmethod
    def assert_can_override_simulation_mode(
        cls,
        override: ManualOverrideRecord,
        is_simulation: bool,
        is_live_disbursal: bool
    ) -> None:
        """
        Fences environment trust. Simulation payloads can never be executed on live banking rails.
        """
        if is_simulation and is_live_disbursal:
            raise NonOverridableInvariantViolationError(
                "NON-OVERRIDABLE INVARIANT: Simulation / mock financial artifacts cannot be routed to live banking disbursals."
            )

    @classmethod
    def assert_can_override_po_quantity(
        cls,
        override: ManualOverrideRecord,
        cumulative_qty: Decimal,
        authorized_po_qty: Decimal
    ) -> None:
        """
        Fences procurement ceilings. Quantity exceeding PO authorization requires a formal PO revision.
        """
        if cumulative_qty > authorized_po_qty:
            raise NonOverridableInvariantViolationError(
                f"NON-OVERRIDABLE INVARIANT: Cumulative invoice quantity ({cumulative_qty}) exceeds authorized "
                f"PO quantity ({authorized_po_qty}). Requires formal PO revision/amendment in ERP."
            )
