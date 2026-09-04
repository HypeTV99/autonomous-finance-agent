from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, Optional
from schemas import PaymentTermsSchedule, PaymentTermsType


class WorkingCapitalScheduler:
    """
    Treasury Working Capital & Dynamic Discounting Engine:
    - Calculates contractual due dates (e.g. Net 30 = Invoice Date + 30 Days).
    - Surfaces 2/10 Net 30 cash discount capture (2% discount if paid within 10 days).
    - Calculates annualized treasury yield on dynamic early discounting:
      Formula: (Discount% / (Full Term - Discount Period)) * 365 days
      For 2/10 Net 30: (2% / 20 days) * 365 = 36.5% Annualized Return on Cash Float.
    """

    @classmethod
    def schedule_payment_terms(
        cls,
        invoice_date_str: str,
        gross_amount: Decimal,
        terms_type: PaymentTermsType = PaymentTermsType.DISCOUNT_2_10_NET_30
    ) -> PaymentTermsSchedule:
        try:
            inv_date = date.fromisoformat(invoice_date_str)
        except Exception:
            inv_date = date.today()

        if terms_type == PaymentTermsType.NET_15:
            terms_desc = "Net 15 Days Commercial Credit"
            due_date = inv_date + timedelta(days=15)
            discount_deadline = None
            disc_rate = 0.0
            savings = Decimal("0.00")
            yield_pct = 0.0
            early_avail = False
        elif terms_type == PaymentTermsType.NET_45:
            terms_desc = "Net 45 Days Commercial Credit"
            due_date = inv_date + timedelta(days=45)
            discount_deadline = None
            disc_rate = 0.0
            savings = Decimal("0.00")
            yield_pct = 0.0
            early_avail = False
        elif terms_type == PaymentTermsType.NET_60:
            terms_desc = "Net 60 Days Commercial Credit"
            due_date = inv_date + timedelta(days=60)
            discount_deadline = None
            disc_rate = 0.0
            savings = Decimal("0.00")
            yield_pct = 0.0
            early_avail = False
        elif terms_type == PaymentTermsType.DISCOUNT_2_10_NET_30:
            terms_desc = "2/10 Net 30 (2% Early Settlement Discount if paid within 10 days)"
            due_date = inv_date + timedelta(days=30)
            disc_date = inv_date + timedelta(days=10)
            discount_deadline = disc_date.isoformat()
            disc_rate = 2.0
            savings = (gross_amount * Decimal("0.02")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            # Annualized Yield = (2% / (30 - 10)) * 365 = 36.5%
            yield_pct = 36.5
            early_avail = date.today() <= disc_date
        else:
            terms_desc = "Net 30 Days Standard Commercial Terms"
            due_date = inv_date + timedelta(days=30)
            discount_deadline = None
            disc_rate = 0.0
            savings = Decimal("0.00")
            yield_pct = 0.0
            early_avail = False

        return PaymentTermsSchedule(
            terms_type=terms_type,
            terms_description=terms_desc,
            invoice_date=inv_date.isoformat(),
            due_date=due_date.isoformat(),
            discount_deadline=discount_deadline,
            discount_rate_pct=disc_rate,
            potential_discount_savings=savings,
            annualized_treasury_yield_pct=yield_pct,
            is_early_discount_available=early_avail
        )
