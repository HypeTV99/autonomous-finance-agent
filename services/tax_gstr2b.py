from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, NamedTuple, Optional
from schemas import GSTR2BStatus


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


class GSTR2BSplitSettlementEngine:
    """
    Indian Statutory Split-Settlement Engine:
    Implements Input Tax Credit (ITC) protection under Section 16(2)(aa) of CGST Act.
    If the invoice has not yet reflected in GSTR-2B:
      - The pre-tax subtotal minus TDS is disbursed immediately (vendor cash flow unblocked).
      - The 18% GST amount is withheld in a retention escrow until vendor files GSTR-1.
    """

    @classmethod
    def calculate_split_settlement(
        cls,
        subtotal: Decimal,
        gst_amount: Decimal,
        tds_amount: Decimal,
        credits_applied: Decimal = Decimal("0.00"),
        gstr2b_status: GSTR2BStatus = GSTR2BStatus.PENDING_SUPPLIER_FILING
    ) -> SplitSettlementResult:
        subtotal = subtotal.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        gst_amount = gst_amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        tds_amount = tds_amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        credits_applied = credits_applied.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        gross_total = subtotal + gst_amount

        # Net immediate base payout (subtotal minus TDS and open credit netting)
        immediate_base = max(Decimal("0.00"), subtotal - tds_amount - credits_applied)

        if gstr2b_status == GSTR2BStatus.MATCHED_IN_2B:
            # Vendor already filed GSTR-1; ITC is guaranteed. Pay base + GST together.
            gst_hold = Decimal("0.00")
            immediate_payout = max(Decimal("0.00"), gross_total - tds_amount - credits_applied)
            status_text = "FULL_CLEARANCE_ITC_GUARANTEED"
            msg = "Invoice confirmed in government GSTR-2B registry. 100% Input Tax Credit secured. Full net settlement authorized."
        else:
            # GSTR-2B pending: hold the GST portion in escrow, disburse base minus TDS
            gst_hold = gst_amount
            immediate_payout = immediate_base
            status_text = "SPLIT_SETTLEMENT_GST_HELD"
            msg = (
                f"GSTR-2B filing pending from vendor. Base subtotal of ₹{subtotal:,.2f} disbursed less TDS (₹{tds_amount:,.2f}). "
                f"GST credit of ₹{gst_amount:,.2f} safely retained in escrow pending GSTR-1 upload."
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
            reconciliation_message=msg
        )
