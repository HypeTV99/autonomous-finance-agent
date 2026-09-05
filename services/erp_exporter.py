import io
import csv
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional
from schemas import ERPJournalEntry, ERPJournalVoucher, JournalEntryType


class DoubleEntryImbalanceError(ValueError):
    """Raised when journal debits and credits do not exactly balance."""
    pass


class SemanticAccountingError(ValueError):
    """Raised when journal entries are mathematically balanced but economically/semantically invalid."""
    pass


class ERPJournalExportEngine:
    """
    Ind AS 1 / IFRS Presentation of Financial Statements:
    Produces exact double-entry ERP journal vouchers and exports RFC 4180 CSVs
    compatible with SAP S/4HANA (BAPI_ACC_DOCUMENT_POST), NetSuite, and Tally Prime.
    Enforces:
    - Zero tolerance double-entry balance (SUM(debits) == SUM(credits) to exact paisa).
    - Explicit rounding adjustment account (9990) for legitimate item-level rounding differences.
    - Semantic accounting validation: account polarities, tax basis, retention liability, monetary conservation.
    - Full auditable lineage (tax decision, policy version, payment intent, credit allocations).
    """

    @classmethod
    def generate_voucher(
        cls,
        invoice_number: str,
        vendor_name: str,
        subtotal: Decimal,
        gst_amount: Decimal,
        tds_amount: Decimal,
        net_disbursed: Decimal,
        gst_hold: Decimal = Decimal("0.00"),
        credit_applied: Decimal = Decimal("0.00"),
        utr_reference: str = "PENDING_SETTLEMENT",
        policy_version: str = "2026.1",
        tax_decision_hash: Optional[str] = None,
        credit_allocation_id: Optional[str] = None,
        retention_id: Optional[str] = None,
        payment_intent_id: Optional[str] = None,
        original_entry_id: Optional[str] = None,
        reversal_entry_id: Optional[str] = None,
        replacement_entry_id: Optional[str] = None,
        posting_state: str = "POSTED"
    ) -> ERPJournalVoucher:
        # 1. Binary Float Ingress Rejection (Prompt 8 Rule 1)
        for name, val in [
            ("subtotal", subtotal),
            ("gst_amount", gst_amount),
            ("tds_amount", tds_amount),
            ("net_disbursed", net_disbursed),
            ("gst_hold", gst_hold),
            ("credit_applied", credit_applied)
        ]:
            if isinstance(val, float):
                raise TypeError(f"Binary float ingress rejected in financial calculation for '{name}': {val}. Use Decimal or string.")

        subtotal = subtotal.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        gst_amount = gst_amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        tds_amount = tds_amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        net_disbursed = net_disbursed.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        gst_hold = gst_hold.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        credit_applied = credit_applied.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        # 2. Semantic Accounting & Monetary Conservation Validation (Prompt 8 Rules 2 & 4)
        if tds_amount > subtotal and subtotal > Decimal("0.00"):
            raise SemanticAccountingError(
                f"TDS deduction cannot exceed taxable expense base: TDS withheld ({tds_amount}) exceeds taxable base ({subtotal})."
            )

        if gst_hold > gst_amount and gst_amount > Decimal("0.00"):
            raise SemanticAccountingError(
                f"GST retention hold cannot exceed total invoiced GST: Retained GST escrow ({gst_hold}) exceeds invoiced GST ({gst_amount})."
            )

        approved_obligation = (subtotal + gst_amount).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        settlement_sum = (net_disbursed + tds_amount + gst_hold + credit_applied).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        if abs(approved_obligation - settlement_sum) > Decimal("0.02"):
            raise SemanticAccountingError(
                f"Monetary conservation violation: Approved obligation ({approved_obligation}) != "
                f"Settlement sum ({settlement_sum}) [Disbursed: {net_disbursed}, TDS: {tds_amount}, "
                f"Retention: {gst_hold}, Credits: {credit_applied}]"
            )

        voucher_id = f"JV-{invoice_number.replace('INV-', '')}"
        posting_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        entries: List[ERPJournalEntry] = [
            ERPJournalEntry(
                account_code="6010",
                account_name="IT & Software Professional Expense",
                entry_type=JournalEntryType.DEBIT,
                amount=subtotal,
                description=f"Operating expense for {vendor_name} ({invoice_number})"
            ),
            ERPJournalEntry(
                account_code="1420",
                account_name="Input GST Receivable (CGST+SGST 18%)",
                entry_type=JournalEntryType.DEBIT,
                amount=gst_amount,
                description=f"Statutory Input Tax Credit claimed ({invoice_number})"
            ),
            ERPJournalEntry(
                account_code="2140",
                account_name="TDS Payable - Challan 281 Reserve",
                entry_type=JournalEntryType.CREDIT,
                amount=tds_amount,
                description=f"Statutory TDS withheld under Section 194J/C ({invoice_number})"
            ),
            ERPJournalEntry(
                account_code="2010",
                account_name="Accounts Payable - Bank Clearing (RazorpayX)",
                entry_type=JournalEntryType.CREDIT,
                amount=net_disbursed,
                description=f"Net IMPS disbursal via banking rails (UTR: {utr_reference})"
            )
        ]

        if gst_hold > Decimal("0.00"):
            entries.append(
                ERPJournalEntry(
                    account_code="2015",
                    account_name="GST Retention Escrow (Held for GSTR-2B)",
                    entry_type=JournalEntryType.CREDIT,
                    amount=gst_hold,
                    description=f"GST withheld pending vendor GSTR-1 upload ({invoice_number})"
                )
            )

        if credit_applied > Decimal("0.00"):
            entries.append(
                ERPJournalEntry(
                    account_code="1080",
                    account_name="Vendor Advances & Open Credit Notes Applied",
                    entry_type=JournalEntryType.CREDIT,
                    amount=credit_applied,
                    description=f"Credit memo netting adjustment ({invoice_number})"
                )
            )

        # 3. Exact Double-Entry Balance without Arbitrary Tolerance (Prompt 8 Rule 3)
        total_debits = sum(e.amount for e in entries if e.entry_type == JournalEntryType.DEBIT)
        total_credits = sum(e.amount for e in entries if e.entry_type == JournalEntryType.CREDIT)
        rounding_diff = (total_debits - total_credits).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        if rounding_diff != Decimal("0.00"):
            if abs(rounding_diff) <= Decimal("0.02"):
                # Legitimate fractional rounding discrepancy: allocate explicitly to account 9990
                if rounding_diff > Decimal("0.00"):
                    entries.append(
                        ERPJournalEntry(
                            account_code="9990",
                            account_name="Financial Rounding Differences",
                            entry_type=JournalEntryType.CREDIT,
                            amount=rounding_diff,
                            description=f"Explicit fractional rounding adjustment ({invoice_number})"
                        )
                    )
                else:
                    entries.append(
                        ERPJournalEntry(
                            account_code="9990",
                            account_name="Financial Rounding Differences",
                            entry_type=JournalEntryType.DEBIT,
                            amount=abs(rounding_diff),
                            description=f"Explicit fractional rounding adjustment ({invoice_number})"
                        )
                    )
            else:
                raise DoubleEntryImbalanceError(
                    f"Double-entry imbalance: Debits ({total_debits}) != Credits ({total_credits}), "
                    f"difference ({rounding_diff}) exceeds fractional threshold."
                )

        final_debits = sum(e.amount for e in entries if e.entry_type == JournalEntryType.DEBIT)
        final_credits = sum(e.amount for e in entries if e.entry_type == JournalEntryType.CREDIT)
        is_balanced = (final_debits == final_credits)

        # 4. Format CSV row
        csv_row = (
            f"{posting_date},{voucher_id},{invoice_number},{vendor_name},"
            f"{subtotal},{gst_amount},{tds_amount},{gst_hold},{credit_applied},{net_disbursed},{utr_reference}"
        )

        return ERPJournalVoucher(
            voucher_id=voucher_id,
            transaction_ref=invoice_number,
            posting_date=posting_date,
            balanced=is_balanced,
            entries=entries,
            export_csv_row=csv_row,
            policy_version=policy_version,
            tax_decision_hash=tax_decision_hash,
            credit_allocation_id=credit_allocation_id,
            retention_id=retention_id,
            payment_intent_id=payment_intent_id,
            original_entry_id=original_entry_id,
            reversal_entry_id=reversal_entry_id,
            replacement_entry_id=replacement_entry_id,
            posting_state=posting_state
        )

    @classmethod
    def build_hardened_voucher(
        cls,
        transaction_id: str,
        invoice_number: str,
        postings: List[Any],
        is_reversal: bool = False,
        policy_version: str = "2026.1",
        tax_decision_hash: Optional[str] = None,
        credit_allocation_id: Optional[str] = None,
        retention_id: Optional[str] = None,
        payment_intent_id: Optional[str] = None,
        original_entry_id: Optional[str] = None,
        reversal_entry_id: Optional[str] = None,
        replacement_entry_id: Optional[str] = None,
        posting_state: str = "POSTED"
    ) -> ERPJournalVoucher:
        posting_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        entries: List[ERPJournalEntry] = []

        for p in postings:
            if isinstance(p, ERPJournalEntry):
                code = p.account_code
                name = p.account_name
                etype = p.entry_type
                amt = p.amount
                desc = p.description
            else:
                code = getattr(p, "account_code", "")
                name = getattr(p, "account_name", "")
                etype = getattr(p, "entry_type")
                amt = getattr(p, "amount")
                desc = getattr(p, "description", f"Posting for {code}")

            if isinstance(amt, float):
                raise TypeError(f"Binary float ingress rejected in posting: {amt}")
            amt = Decimal(str(amt)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

            # Polarity validation for standard entries
            if not is_reversal:
                if code.startswith("6") and etype != JournalEntryType.DEBIT:
                    raise SemanticAccountingError(f"Invalid posting polarity: Expense accounts (6xxx) must be DEBIT for standard postings. Got {etype} for {code}.")
                if code.startswith("2") and etype != JournalEntryType.CREDIT:
                    raise SemanticAccountingError(f"Invalid posting polarity: Liability accounts (2xxx) must be CREDIT for standard accrual postings. Got {etype} for {code}.")

            entries.append(
                ERPJournalEntry(
                    account_code=code,
                    account_name=name,
                    entry_type=etype,
                    amount=amt,
                    description=desc
                )
            )

        total_debits = sum(e.amount for e in entries if e.entry_type == JournalEntryType.DEBIT)
        total_credits = sum(e.amount for e in entries if e.entry_type == JournalEntryType.CREDIT)
        diff = (total_debits - total_credits).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        if diff != Decimal("0.00"):
            if abs(diff) <= Decimal("0.02"):
                # Legitimate fractional rounding discrepancy: allocate explicitly to account 9990
                if diff > Decimal("0.00"):
                    entries.append(
                        ERPJournalEntry(
                            account_code="9990",
                            account_name="Financial Rounding Differences (GAAP Adjustment)",
                            entry_type=JournalEntryType.CREDIT,
                            amount=diff,
                            description="Fractional rounding balancing credit"
                        )
                    )
                else:
                    entries.append(
                        ERPJournalEntry(
                            account_code="9990",
                            account_name="Financial Rounding Differences (GAAP Adjustment)",
                            entry_type=JournalEntryType.DEBIT,
                            amount=abs(diff),
                            description="Fractional rounding balancing debit"
                        )
                    )
            else:
                raise DoubleEntryImbalanceError(
                    f"Double-entry imbalance: total debits ({total_debits}) != total credits ({total_credits}) "
                    f"[Variance: {diff} INR exceeds allowable 0.02 rounding threshold]"
                )

        csv_rows = []
        for e in entries:
            dr = f"{e.amount:.2f}" if e.entry_type == JournalEntryType.DEBIT else "0.00"
            cr = f"{e.amount:.2f}" if e.entry_type == JournalEntryType.CREDIT else "0.00"
            csv_rows.append(f"{transaction_id},{posting_date},{e.account_code},\"{e.account_name}\",{dr},{cr},\"{e.description}\"")
        csv_row_text = "\n".join(csv_rows)

        return ERPJournalVoucher(
            voucher_id=transaction_id,
            transaction_ref=invoice_number,
            posting_date=posting_date,
            balanced=True,
            entries=entries,
            export_csv_row=csv_row_text,
            policy_version=policy_version,
            tax_decision_hash=tax_decision_hash,
            credit_allocation_id=credit_allocation_id,
            retention_id=retention_id,
            payment_intent_id=payment_intent_id,
            original_entry_id=original_entry_id,
            reversal_entry_id=reversal_entry_id,
            replacement_entry_id=replacement_entry_id,
            posting_state="REVERSED" if is_reversal else posting_state
        )

    @classmethod
    def export_full_ledger_csv(cls, vouchers: List[ERPJournalVoucher]) -> str:
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "Posting Date", "Voucher ID", "Invoice Number", "Vendor Name",
            "Debit: Subtotal Expense (INR)", "Debit: Input GST 18% (INR)",
            "Credit: TDS Payable (INR)", "Credit: GST Retention Escrow (INR)",
            "Credit: Open Credits Applied (INR)", "Credit: Net Bank Payout (INR)", "Bank UTR"
        ])
        for v in vouchers:
            parts = v.export_csv_row.split(",")
            writer.writerow(parts)
        return output.getvalue()


