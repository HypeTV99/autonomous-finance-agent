import io
import csv
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List
from schemas import ERPJournalEntry, ERPJournalVoucher, JournalEntryType


class ERPJournalExportEngine:
    """
    Ind AS 1 / IFRS Presentation of Financial Statements:
    Produces balanced double-entry ERP journal vouchers and exports RFC 4180 CSVs
    compatible with SAP S/4HANA (BAPI_ACC_DOCUMENT_POST), NetSuite, and Tally Prime.
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
        utr_reference: str = "PENDING_SETTLEMENT"
    ) -> ERPJournalVoucher:
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

        total_debits = sum(e.amount for e in entries if e.entry_type == JournalEntryType.DEBIT)
        total_credits = sum(e.amount for e in entries if e.entry_type == JournalEntryType.CREDIT)
        is_balanced = abs(total_debits - total_credits) <= Decimal("0.05")

        # Format CSV row
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
            export_csv_row=csv_row
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
