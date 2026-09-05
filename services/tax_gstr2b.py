from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, NamedTuple, Optional, Tuple
import uuid

from schemas import (
    FinancialPosition,
    GSTR2BStatus,
    RetentionLifecycleState,
    RetentionRecord,
)


class SplitSettlementResult(NamedTuple):
    subtotal_pre_gst: Decimal
    gst_amount: Decimal
    tds_withheld: Decimal
    credits_applied: Decimal
    immediate_base_disbursal: Decimal
    gst_retention_escrow: Decimal
    challan_281_reserve: Decimal
    total_invoiced_gross: Decimal
    gstr2b_status: GSTR2BStatus
    settlement_status: str
    reconciliation_message: str
    financial_position: Optional[FinancialPosition] = None
    retention_record: Optional[RetentionRecord] = None


class GSTR2BSplitSettlementEngine:
    """
    Indian Statutory Split-Settlement Engine:
    Implements Input Tax Credit (ITC) protection under Section 16(2)(aa) of CGST Act.
    If the invoice has not yet reflected in GSTR-2B:
      - The pre-tax subtotal minus TDS is disbursed immediately (vendor cash flow unblocked).
      - The GST amount is withheld in a retention escrow until vendor files GSTR-1,
        provided that commercial contract terms permit retention and policy is active.
    """

    @classmethod
    def calculate_split_settlement(
        cls,
        subtotal: Decimal,
        gst_amount: Decimal,
        tds_amount: Decimal,
        credits_applied: Decimal = Decimal("0.00"),
        gstr2b_status: GSTR2BStatus = GSTR2BStatus.PENDING_SUPPLIER_FILING,
        contract_permits_retention: bool = True,
        retention_policy_active: bool = True,
        policy_version: str = "2026.1",
        invoice_number: Optional[str] = None,
        vendor_id: Optional[str] = None,
        store: Optional[Any] = None
    ) -> SplitSettlementResult:
        subtotal = subtotal.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        gst_amount = gst_amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        tds_amount = tds_amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        credits_applied = credits_applied.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        gross_total = subtotal + gst_amount

        # Net immediate base payout (subtotal minus TDS and open credit netting)
        immediate_base = max(Decimal("0.00"), subtotal - tds_amount - credits_applied)

        ret_record: Optional[RetentionRecord] = None

        is_matched = gstr2b_status in (GSTR2BStatus.MATCHED, GSTR2BStatus.MATCHED_IN_2B)

        if is_matched:
            # Vendor already filed GSTR-1; ITC is guaranteed. Pay base + GST together.
            gst_hold = Decimal("0.00")
            immediate_payout = max(Decimal("0.00"), gross_total - tds_amount - credits_applied)
            status_text = "FULL_CLEARANCE_ITC_GUARANTEED"
            msg = "Invoice confirmed in government GSTR-2B registry. 100% Input Tax Credit secured. Full net settlement authorized."
        else:
            # GSTR-2B not matched: check if commercial contract and active policy permit retention
            if contract_permits_retention and retention_policy_active and gst_amount > Decimal("0.00"):
                gst_hold = gst_amount
                immediate_payout = immediate_base
                status_text = "SPLIT_SETTLEMENT_GST_HELD"
                msg = (
                    f"GSTR-2B filing pending from vendor ({gstr2b_status.value}). Base subtotal of ₹{subtotal:,.2f} disbursed less TDS (₹{tds_amount:,.2f}). "
                    f"GST credit of ₹{gst_amount:,.2f} safely retained in escrow pending GSTR-1 upload."
                )
                now_iso = datetime.now(timezone.utc).isoformat()
                ret_id = f"RET-{invoice_number or 'INV'}-{uuid.uuid4().hex[:8].upper()}"
                ret_record = RetentionRecord(
                    retention_id=ret_id,
                    invoice_number=invoice_number or "UNKNOWN",
                    vendor_id=vendor_id or "UNKNOWN",
                    policy_id="POL-GST-RETENTION-CGST16",
                    policy_version=policy_version,
                    retained_amount=gst_hold,
                    released_amount=Decimal("0.00"),
                    remaining_amount=gst_hold,
                    reason=f"GSTR-2B status '{gstr2b_status.value}': ITC protection under Sec 16(2)(aa) CGST Act",
                    release_condition="GSTR-2B reflection with matching invoice reference and taxable values",
                    state=RetentionLifecycleState.AWAITING_EVIDENCE,
                    release_history=[],
                    created_at=now_iso,
                    updated_at=now_iso
                )
                if store and hasattr(store, "save_retention_record"):
                    store.save_retention_record(ret_record.model_dump(mode="json"))
            else:
                # Contract prohibits retention or policy inactive: cannot withhold
                gst_hold = Decimal("0.00")
                immediate_payout = max(Decimal("0.00"), gross_total - tds_amount - credits_applied)
                if not contract_permits_retention:
                    status_text = "CONTRACT_PROHIBITS_RETENTION_FULL_DISBURSED"
                    msg = (
                        f"GSTR-2B status is '{gstr2b_status.value}', but commercial contract prohibits GST retention escrow. "
                        f"Full gross amount ₹{gross_total:,.2f} less TDS/credits disbursed per contract terms."
                    )
                else:
                    status_text = "RETENTION_POLICY_INACTIVE_FULL_DISBURSED"
                    msg = (
                        f"GSTR-2B status is '{gstr2b_status.value}', but retention policy is inactive. "
                        f"Full gross amount ₹{gross_total:,.2f} less TDS/credits disbursed."
                    )

        # Mathematical Financial Position domain separation
        fin_pos = FinancialPosition(
            gross_invoice_amount=gross_total,
            base_amount=subtotal,
            gst_amount=gst_amount,
            tds_amount=tds_amount,
            credit_amount=credits_applied,
            contractual_retention_amount=gst_hold,
            immediate_payment_amount=immediate_payout
        )

        return SplitSettlementResult(
            subtotal_pre_gst=subtotal,
            gst_amount=gst_amount,
            tds_withheld=tds_amount,
            credits_applied=credits_applied,
            immediate_base_disbursal=immediate_payout,
            gst_retention_escrow=gst_hold,
            challan_281_reserve=tds_amount,
            total_invoiced_gross=gross_total,
            gstr2b_status=gstr2b_status,
            settlement_status=status_text,
            reconciliation_message=msg,
            financial_position=fin_pos,
            retention_record=ret_record
        )

    @classmethod
    def release_retention(
        cls,
        retention_id: str,
        release_amount: Optional[Decimal] = None,
        evidence_reference: str = "",
        store: Optional[Any] = None,
        record: Optional[RetentionRecord] = None
    ) -> Tuple[bool, Optional[RetentionRecord], str]:
        """
        Policy-driven idempotent release of retained GST escrow funds.
        - Fences against duplicate releases (idempotent).
        - Blocks release if retention is DISPUTED or EXPIRED.
        - Handles partial releases, updating remaining and released amounts.
        - Persists update to store.
        """
        target_record: Optional[RetentionRecord] = record
        if target_record is None and store and hasattr(store, "get_retention_record"):
            data = store.get_retention_record(retention_id)
            if data:
                target_record = RetentionRecord(**data)

        if not target_record:
            return False, None, f"Retention record '{retention_id}' not found."

        # Check terminal / fenced states
        if target_record.state == RetentionLifecycleState.RELEASED:
            return True, target_record, f"Idempotent: Retention '{retention_id}' already fully released."

        if target_record.state == RetentionLifecycleState.DISPUTED:
            return False, target_record, f"Release blocked: Retention '{retention_id}' is in DISPUTED state."

        if target_record.state == RetentionLifecycleState.EXPIRED:
            return False, target_record, f"Release blocked: Retention '{retention_id}' has EXPIRED."

        # Determine release amount
        if release_amount is None or release_amount >= target_record.remaining_amount:
            amount_to_release = target_record.remaining_amount
            new_state = RetentionLifecycleState.RELEASED
            new_remaining = Decimal("0.00")
            new_released = (target_record.released_amount + amount_to_release).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        else:
            amount_to_release = release_amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            if amount_to_release <= Decimal("0.00"):
                return False, target_record, "Release amount must be greater than zero."
            new_state = RetentionLifecycleState.PARTIAL_RELEASE
            new_remaining = (target_record.remaining_amount - amount_to_release).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            new_released = (target_record.released_amount + amount_to_release).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        now_iso = datetime.now(timezone.utc).isoformat()
        history_entry = {
            "released_at": now_iso,
            "amount": str(amount_to_release),
            "evidence_reference": evidence_reference,
            "resulting_state": new_state.value
        }

        target_record.released_amount = new_released
        target_record.remaining_amount = new_remaining
        target_record.state = new_state
        target_record.release_history.append(history_entry)
        target_record.updated_at = now_iso

        if store and hasattr(store, "update_retention_record"):
            store.update_retention_record(
                retention_id=retention_id,
                update_dict=target_record.model_dump(mode="json")
            )

        return True, target_record, f"Successfully released ₹{amount_to_release:,.2f} from retention escrow."
