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
        terms_type: PaymentTermsType = PaymentTermsType.DISCOUNT_2_10_NET_30,
        cost_of_capital_pct: Optional[float] = None,
        liquidity_cost_pct: Optional[float] = None
    ) -> PaymentTermsSchedule:
        if isinstance(gross_amount, float):
            raise TypeError(
                f"Binary float ingress rejected for gross_amount={gross_amount}. "
                f"Monetary amounts must be exact Decimal, integer, or numeric string."
            )
        gross_amount = Decimal(str(gross_amount)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        try:
            inv_date = date.fromisoformat(invoice_date_str)
        except Exception:
            inv_date = date.today()

        simple_apr = 0.0
        effective_ear = 0.0
        net_benefit = Decimal("0.00")

        if terms_type == PaymentTermsType.NET_15:
            terms_desc = "Net 15 Days Commercial Credit"
            due_date = inv_date + timedelta(days=15)
            discount_deadline = None
            disc_rate = 0.0
            savings = Decimal("0.00")
            yield_pct = 0.0
            early_avail = False
            recommendation = "PAY_AT_MATURITY"
            explanation = f"Standard credit terms without early settlement discount. Disburse on {due_date.isoformat()}."
        elif terms_type == PaymentTermsType.NET_45:
            terms_desc = "Net 45 Days Commercial Credit"
            due_date = inv_date + timedelta(days=45)
            discount_deadline = None
            disc_rate = 0.0
            savings = Decimal("0.00")
            yield_pct = 0.0
            early_avail = False
            recommendation = "PAY_AT_MATURITY"
            explanation = f"Standard credit terms without early settlement discount. Disburse on {due_date.isoformat()}."
        elif terms_type == PaymentTermsType.NET_60:
            terms_desc = "Net 60 Days Commercial Credit"
            due_date = inv_date + timedelta(days=60)
            discount_deadline = None
            disc_rate = 0.0
            savings = Decimal("0.00")
            yield_pct = 0.0
            early_avail = False
            recommendation = "PAY_AT_MATURITY"
            explanation = f"Standard credit terms without early settlement discount. Disburse on {due_date.isoformat()}."
        elif terms_type == PaymentTermsType.DISCOUNT_2_10_NET_30:
            terms_desc = "2/10 Net 30 (2% Early Settlement Discount if paid within 10 days)"
            due_date = inv_date + timedelta(days=30)
            disc_date = inv_date + timedelta(days=10)
            discount_deadline = disc_date.isoformat()
            disc_rate = 2.0
            savings = (gross_amount * Decimal("0.02")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            
            # Simple Annualized Return (Nominal APR) = (2% / 20 days) * 365 = 36.5%
            simple_apr = 36.5
            yield_pct = simple_apr
            
            # Effective Annualized Return (Compounded EAR) = ((1 + 0.02/0.98)^(365/20) - 1) * 100 = 44.59%
            effective_ear = 44.59
            
            early_avail = date.today() <= disc_date

            if cost_of_capital_pct is not None:
                total_hurdle = float(cost_of_capital_pct) + (float(liquidity_cost_pct) if liquidity_cost_pct else 0.0)
                hurdle_dec = Decimal(str(total_hurdle)) / Decimal("100")
                discounted_payment = gross_amount - savings
                financing_cost = (discounted_payment * hurdle_dec * Decimal("20") / Decimal("365")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                net_benefit = savings - financing_cost

                if simple_apr > total_hurdle and net_benefit > Decimal("0.00"):
                    recommendation = "TAKE_EARLY_DISCOUNT"
                    explanation = (
                        f"Early discount simple yield of {simple_apr:.1f}% (effective EAR {effective_ear:.2f}%) "
                        f"exceeds hurdle rate of {total_hurdle:.1f}%, generating net economic benefit of Rs.{net_benefit}."
                    )
                else:
                    recommendation = "HOLD_CASH_FULL_TERM"
                    explanation = (
                        f"Hurdle rate of {total_hurdle:.1f}% exceeds or eliminates net benefit of early discount "
                        f"(net benefit: Rs.{net_benefit}). Recommend holding cash until full maturity."
                    )
            else:
                net_benefit = savings
                if early_avail:
                    recommendation = "TAKE_EARLY_DISCOUNT"
                    explanation = "Capturing 2% discount generates simple annualized return of 36.5% (effective EAR 44.59%) on 20 days cash float."
                else:
                    recommendation = "HOLD_CASH_FULL_TERM"
                    explanation = "Early discount window has expired. Pay at full term maturity."
        else:
            terms_desc = "Net 30 Days Standard Commercial Terms"
            due_date = inv_date + timedelta(days=30)
            discount_deadline = None
            disc_rate = 0.0
            savings = Decimal("0.00")
            yield_pct = 0.0
            early_avail = False
            recommendation = "PAY_AT_MATURITY"
            explanation = f"Standard credit terms without early settlement discount. Disburse on {due_date.isoformat()}."

        return PaymentTermsSchedule(
            terms_type=terms_type,
            terms_description=terms_desc,
            invoice_date=inv_date.isoformat(),
            due_date=due_date.isoformat(),
            discount_deadline=discount_deadline,
            discount_rate_pct=disc_rate,
            potential_discount_savings=savings,
            annualized_treasury_yield_pct=yield_pct,
            is_early_discount_available=early_avail,
            simple_annualized_return_pct=simple_apr,
            effective_annualized_return_pct=effective_ear,
            cost_of_capital_pct=cost_of_capital_pct,
            liquidity_cost_pct=liquidity_cost_pct,
            net_economic_benefit=net_benefit,
            recommendation=recommendation,
            explanation=explanation
        )
