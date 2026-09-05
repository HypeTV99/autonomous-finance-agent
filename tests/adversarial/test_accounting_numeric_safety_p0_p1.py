from datetime import date, datetime, timezone
from decimal import Decimal
import pytest
from pydantic import ValidationError

from schemas import (
    DoubleEntryJournal,
    ERPJournalVoucher,
    ExtractedInvoicePayload,
    InvoiceLineItem,
    JournalEntryType,
    LedgerPosting,
    PaymentTermsSchedule,
    PaymentTermsType,
    TaxCalculationResult,
    TDSSection,
)
from services.erp_exporter import (
    DoubleEntryImbalanceError,
    ERPJournalExportEngine,
    SemanticAccountingError,
)
from services.working_capital import WorkingCapitalScheduler
from firestore_store import FirestoreStateStore, PostedJournalMutationError


# ============================================================================
# TEST 1: Binary Float Ingress Rejected in Financial Paths
# ============================================================================
def test_binary_float_ingress_rejected():
    """Verifies binary float ingress is rejected across schemas, ERP exporters, and working capital."""
    # 1. InvoiceLineItem rejects float unit_price and quantity
    with pytest.raises((ValidationError, TypeError)) as exc:
        InvoiceLineItem(
            description="Consulting Services",
            quantity=Decimal("1.0"),
            unit_price=1500.50,  # float
            item_total=Decimal("1500.50")
        )
    assert "Binary float ingress rejected" in str(exc.value)

    with pytest.raises((ValidationError, TypeError)) as exc:
        InvoiceLineItem(
            description="Consulting Services",
            quantity=2.5,  # float
            unit_price=Decimal("1000.00"),
            item_total=Decimal("2500.00")
        )
    assert "Binary float ingress rejected" in str(exc.value)

    # 2. ExtractedInvoicePayload rejects float subtotal
    with pytest.raises((ValidationError, TypeError)) as exc:
        ExtractedInvoicePayload(
            invoice_number="INV-FLOAT-01",
            vendor_name="Alpha Tech Labs",
            vendor_pan="AAACT1234F",
            subtotal=10000.00,  # float
            tax_amount=Decimal("1800.00"),
            total_amount=Decimal("11800.00")
        )
    assert "Binary float ingress rejected" in str(exc.value)

    # 3. ERPJournalExportEngine rejects float arguments
    with pytest.raises(TypeError) as exc:
        ERPJournalExportEngine.generate_voucher(
            invoice_number="INV-FLOAT-02",
            vendor_name="Alpha Tech Labs",
            subtotal=100000.00,  # float
            gst_amount=Decimal("18000.00"),
            tds_amount=Decimal("2000.00"),
            net_disbursed=Decimal("98000.00")
        )
    assert "Binary float ingress rejected" in str(exc.value)

    # 4. WorkingCapitalScheduler rejects float gross_amount
    with pytest.raises(TypeError) as exc:
        WorkingCapitalScheduler.schedule_payment_terms(
            invoice_date_str="2026-09-01",
            gross_amount=50000.00,  # float
            terms_type=PaymentTermsType.DISCOUNT_2_10_NET_30
        )
    assert "Binary float ingress rejected" in str(exc.value)


# ============================================================================
# TEST 2: Exact Double-Entry Balance (No Arbitrary Tolerance)
# ============================================================================
def test_exact_double_entry_balance_no_arbitrary_tolerance():
    """Verifies that arbitrary tolerance (e.g. 0.05) is removed, requiring exact balance or <=0.02 explicit rounding."""
    # Perfectly balanced voucher succeeds
    voucher = ERPJournalExportEngine.generate_voucher(
        invoice_number="INV-EXACT-01",
        vendor_name="Apex Solutions",
        subtotal=Decimal("100000.00"),
        gst_amount=Decimal("18000.00"),
        tds_amount=Decimal("2000.00"),
        net_disbursed=Decimal("116000.00"),
        gst_hold=Decimal("0.00"),
        credit_applied=Decimal("0.00")
    )
    assert voucher.balanced is True
    assert voucher.total_debits == Decimal("118000.00")
    assert voucher.total_credits == Decimal("118000.00")

    # Unbalanced by 0.05 (the legacy arbitrary tolerance) MUST raise DoubleEntryImbalanceError
    postings_imbalanced = [
        LedgerPosting(
            account_name="EXP-6010 - Direct Vendor Procurement & Services",
            account_code="6010",
            entry_type=JournalEntryType.DEBIT,
            amount=Decimal("100.00")
        ),
        LedgerPosting(
            account_name="LIAB-2010 - Accounts Payable",
            account_code="2010",
            entry_type=JournalEntryType.CREDIT,
            amount=Decimal("100.05")  # 5 paise drift
        )
    ]
    with pytest.raises(DoubleEntryImbalanceError) as exc:
        ERPJournalExportEngine.build_hardened_voucher(
            transaction_id="GL-TEST-IMBAL",
            invoice_number="INV-TEST",
            postings=postings_imbalanced
        )
    assert "imbalance" in str(exc.value).lower()

    # Small legitimate 1-paisa rounding difference <= 0.02 is explicitly balanced to account 9990
    postings_with_paisa = [
        LedgerPosting(
            account_name="EXP-6010 - Direct Vendor Procurement & Services",
            account_code="6010",
            entry_type=JournalEntryType.DEBIT,
            amount=Decimal("100.00")
        ),
        LedgerPosting(
            account_name="LIAB-2010 - Accounts Payable",
            account_code="2010",
            entry_type=JournalEntryType.CREDIT,
            amount=Decimal("99.99")  # 1 paisa discrepancy
        )
    ]
    balanced_voucher = ERPJournalExportEngine.build_hardened_voucher(
        transaction_id="GL-TEST-ROUNDING",
        invoice_number="INV-TEST",
        postings=postings_with_paisa
    )
    assert balanced_voucher.balanced is True
    assert balanced_voucher.total_debits == balanced_voucher.total_credits == Decimal("100.00")
    # Verify account 9990 received the 1-paisa adjustment
    rounding_postings = [p for p in balanced_voucher.journal_entries if p.account_code == "9990"]
    assert len(rounding_postings) == 1
    assert rounding_postings[0].amount == Decimal("0.01")
    assert rounding_postings[0].entry_type == JournalEntryType.CREDIT


# ============================================================================
# TEST 3: Balanced But Economically Wrong Journal Rejected
# ============================================================================
def test_balanced_but_economically_wrong_journal_rejected():
    """Verifies that journals where settlement sum != economic obligation raise SemanticAccountingError."""
    # Subtotal 100,000 + GST 18,000 = Obligation 118,000
    # But settlement specifies net_disbursed 90,000 + TDS 2,000 = 92,000 (gap of 26,000 unaccounted for)
    with pytest.raises(SemanticAccountingError) as exc:
        ERPJournalExportEngine.generate_voucher(
            invoice_number="INV-SEMANTIC-01",
            vendor_name="Apex Solutions",
            subtotal=Decimal("100000.00"),
            gst_amount=Decimal("18000.00"),
            tds_amount=Decimal("2000.00"),
            net_disbursed=Decimal("90000.00"),  # Settlement gap: 118,000 != 92,000
            gst_hold=Decimal("0.00"),
            credit_applied=Decimal("0.00")
        )
    assert "Monetary conservation violation" in str(exc.value)


# ============================================================================
# TEST 4: Account Polarity Validation
# ============================================================================
def test_account_polarity_validation():
    """Verifies that account polarities (Expense=Debit, Asset=Debit, Liability=Credit) are enforced."""
    # Invalid polarity: Expense (6010) credited and Liability (2010) debited outside of reversal
    invalid_polarity_postings = [
        LedgerPosting(
            account_name="EXP-6010 - Direct Vendor Procurement & Services",
            account_code="6010",
            entry_type=JournalEntryType.CREDIT,  # Wrong polarity for standard entry
            amount=Decimal("10000.00")
        ),
        LedgerPosting(
            account_name="LIAB-2010 - Accounts Payable",
            account_code="2010",
            entry_type=JournalEntryType.DEBIT,   # Wrong polarity for standard entry
            amount=Decimal("10000.00")
        )
    ]
    with pytest.raises(SemanticAccountingError) as exc:
        ERPJournalExportEngine.build_hardened_voucher(
            transaction_id="GL-WRONG-POLARITY",
            invoice_number="INV-POLARITY-01",
            postings=invalid_polarity_postings,
            is_reversal=False
        )
    assert "Invalid posting polarity" in str(exc.value)

    # In reversal mode, inverted polarities ARE valid
    reversal_voucher = ERPJournalExportEngine.build_hardened_voucher(
        transaction_id="REV-GL-WRONG-POLARITY",
        invoice_number="INV-POLARITY-01",
        postings=invalid_polarity_postings,
        is_reversal=True
    )
    assert reversal_voucher.balanced is True
    assert reversal_voucher.posting_state == "REVERSED"


# ============================================================================
# TEST 5: Tax and Retention Basis Consistency
# ============================================================================
def test_tax_and_retention_basis_consistency():
    """Verifies TDS deduction cannot exceed taxable base and GST hold cannot exceed invoiced GST."""
    # Case A: TDS exceeds subtotal
    with pytest.raises(SemanticAccountingError) as exc:
        ERPJournalExportEngine.generate_voucher(
            invoice_number="INV-TAX-BASIS-01",
            vendor_name="Apex Solutions",
            subtotal=Decimal("10000.00"),
            gst_amount=Decimal("1800.00"),
            tds_amount=Decimal("15000.00"),  # TDS > Subtotal
            net_disbursed=Decimal("0.00"),
            gst_hold=Decimal("0.00"),
            credit_applied=Decimal("0.00")
        )
    assert "TDS deduction cannot exceed taxable expense base" in str(exc.value)

    # Case B: GST retention hold exceeds invoiced GST
    with pytest.raises(SemanticAccountingError) as exc:
        ERPJournalExportEngine.generate_voucher(
            invoice_number="INV-RET-BASIS-01",
            vendor_name="Apex Solutions",
            subtotal=Decimal("10000.00"),
            gst_amount=Decimal("1800.00"),
            tds_amount=Decimal("1000.00"),
            net_disbursed=Decimal("8300.00"),
            gst_hold=Decimal("2500.00"),  # GST hold > GST amount
            credit_applied=Decimal("0.00")
        )
    assert "GST retention hold cannot exceed total invoiced GST" in str(exc.value)


# ============================================================================
# TEST 6: Monetary Conservation in Multi-Component Settlement
# ============================================================================
def test_monetary_conservation_in_accounting():
    """Verifies Cash + TDS + Retention + Credits == Approved Obligation with split escrow settlement."""
    subtotal = Decimal("500000.00")
    gst = Decimal("90000.00")
    obligation = subtotal + gst  # 590,000.00

    tds = Decimal("50000.00")       # 10% on 500,000
    gst_hold = Decimal("90000.00")  # 100% GST retention held
    credit = Decimal("50000.00")    # Pre-existing credit note applied
    cash_disbursed = obligation - tds - gst_hold - credit  # 400,000.00

    voucher = ERPJournalExportEngine.generate_voucher(
        invoice_number="INV-CONSERVE-01",
        vendor_name="Mega Enterprise Corp",
        subtotal=subtotal,
        gst_amount=gst,
        tds_amount=tds,
        net_disbursed=cash_disbursed,
        gst_hold=gst_hold,
        credit_applied=credit,
        utr_reference="UTR-HDFC-991823"
    )

    assert voucher.balanced is True
    assert voucher.total_debits == Decimal("590000.00")
    assert voucher.total_credits == Decimal("590000.00")

    # Verify each component is distinctly posted in the ledger voucher
    postings = {p.account_code: p for p in voucher.journal_entries}
    assert postings["6010"].amount == subtotal        # Expense Debit
    assert postings["1420"].amount == gst             # Input GST Debit
    assert postings["2010"].amount == cash_disbursed  # AP Cash Credit
    assert postings["2140"].amount == tds             # TDS Payable Credit
    assert postings["2015"].amount == gst_hold        # Escrow Retention Credit
    assert postings["1080"].amount == credit          # Advance/Credit Consumed Credit


# ============================================================================
# TEST 7: Posted Journal Mutation Blocked
# ============================================================================
def test_posted_journal_mutation_blocked():
    """Verifies that an existing posted journal entry cannot be mutated in place."""
    store = FirestoreStateStore()
    txn_id = "GL-POSTED-IMMUTABLE-01"

    journal_dict = {
        "transaction_id": txn_id,
        "invoice_number": "INV-IMMUTABLE-01",
        "postings": [
            {"account_name": "EXP-6010", "account_code": "6010", "entry_type": "DEBIT", "amount": "1000.00"},
            {"account_name": "LIAB-2010", "account_code": "2010", "entry_type": "CREDIT", "amount": "1000.00"}
        ],
        "posting_state": "ACTIVE"
    }
    challan_dict = {"tds_amount": "0.00", "vendor_pan": "AAACT1234F"}

    # Initial posting succeeds
    store.persist_general_ledger(journal_dict, challan_dict)
    posted = store.get_general_ledger(txn_id)
    assert posted is not None
    assert posted["status"] == "ACTIVE"

    # Attempt to mutate amounts or postings under the same transaction_id MUST raise PostedJournalMutationError
    mutated_journal = dict(journal_dict)
    mutated_journal["postings"] = [
        {"account_name": "EXP-6010", "account_code": "6010", "entry_type": "DEBIT", "amount": "5000.00"},
        {"account_name": "LIAB-2010", "account_code": "2010", "entry_type": "CREDIT", "amount": "5000.00"}
    ]

    with pytest.raises(PostedJournalMutationError) as exc:
        store.persist_general_ledger(mutated_journal, challan_dict)
    assert "Cannot mutate posted journal entry" in str(exc.value)

    # Verify original record in store remains uncorrupted
    unaltered = store.get_general_ledger(txn_id)
    assert unaltered["journal"]["postings"][0]["amount"] == "1000.00"


# ============================================================================
# TEST 8: Idempotent Journal Posting
# ============================================================================
def test_idempotent_journal_posting():
    """Verifies identical journal payloads are accepted idempotently without error."""
    store = FirestoreStateStore()
    txn_id = "GL-POSTED-IDEMPOTENT-01"

    journal_dict = {
        "transaction_id": txn_id,
        "invoice_number": "INV-IDEM-01",
        "postings": [
            {"account_name": "EXP-6010", "account_code": "6010", "entry_type": "DEBIT", "amount": "2000.00"},
            {"account_name": "LIAB-2010", "account_code": "2010", "entry_type": "CREDIT", "amount": "2000.00"}
        ],
        "posting_state": "ACTIVE"
    }
    challan_dict = {"tds_amount": "0.00", "vendor_pan": "AAACT1234F"}

    # First call succeeds
    store.persist_general_ledger(journal_dict, challan_dict)
    first_record = store.get_general_ledger(txn_id)

    # Second identical call succeeds without error
    store.persist_general_ledger(journal_dict, challan_dict)
    second_record = store.get_general_ledger(txn_id)

    assert first_record["journal"] == second_record["journal"]
    assert second_record["status"] == "ACTIVE"


# ============================================================================
# TEST 9: Reversal and Replacement Lineage
# ============================================================================
def test_reversal_and_replacement_lineage():
    """Verifies that journal reversal creates inverted entries, and replacement maintains complete lineage."""
    store = FirestoreStateStore()

    # 1. Post original journal
    orig_txn_id = "GL-ORIG-01"
    orig_journal = {
        "transaction_id": orig_txn_id,
        "invoice_number": "INV-REV-01",
        "postings": [
            {"account_name": "EXP-6010", "account_code": "6010", "entry_type": "DEBIT", "amount": "10000.00"},
            {"account_name": "LIAB-2010", "account_code": "2010", "entry_type": "CREDIT", "amount": "10000.00"}
        ],
        "posting_state": "ACTIVE"
    }
    challan = {"tds_amount": "0.00", "vendor_pan": "AAACT1234F"}
    store.persist_general_ledger(orig_journal, challan)

    # 2. Reverse original journal
    rev_payload = store.reverse_general_ledger(
        original_txn_id=orig_txn_id,
        reason="Vendor overbilled line item",
        actor="CHIEF_ACCOUNTANT"
    )
    rev_txn_id = rev_payload["journal"]["transaction_id"]
    assert rev_txn_id == f"REV-{orig_txn_id}"
    assert rev_payload["original_entry_id"] == orig_txn_id
    assert rev_payload["reason"] == "Vendor overbilled line item"
    assert rev_payload["actor"] == "CHIEF_ACCOUNTANT"

    # Verify debits and credits were strictly inverted in reversal postings
    rev_postings = rev_payload["journal"]["postings"]
    exp_rev = [p for p in rev_postings if p["account_code"] == "6010"][0]
    ap_rev = [p for p in rev_postings if p["account_code"] == "2010"][0]
    assert exp_rev["entry_type"] == "CREDIT"
    assert ap_rev["entry_type"] == "DEBIT"

    # Verify original journal is now marked REVERSED with pointer to reversal
    orig_updated = store.get_general_ledger(orig_txn_id)
    assert orig_updated["status"] == "REVERSED"
    assert orig_updated["reversal_entry_id"] == rev_txn_id

    # 3. Post a replacement journal with full forward and backward lineage
    orig_txn_2 = "GL-ORIG-02"
    orig_journal_2 = {
        "transaction_id": orig_txn_2,
        "invoice_number": "INV-REV-02",
        "postings": [
            {"account_name": "EXP-6010", "account_code": "6010", "entry_type": "DEBIT", "amount": "20000.00"},
            {"account_name": "LIAB-2010", "account_code": "2010", "entry_type": "CREDIT", "amount": "20000.00"}
        ],
        "posting_state": "ACTIVE"
    }
    store.persist_general_ledger(orig_journal_2, challan)

    replacement_journal = {
        "transaction_id": "GL-REPLACEMENT-02",
        "invoice_number": "INV-REV-02",
        "postings": [
            {"account_name": "EXP-6010", "account_code": "6010", "entry_type": "DEBIT", "amount": "18000.00"},
            {"account_name": "LIAB-2010", "account_code": "2010", "entry_type": "CREDIT", "amount": "18000.00"}
        ],
        "posting_state": "ACTIVE"
    }

    rev_p2, rep_p2 = store.replace_general_ledger(
        original_txn_id=orig_txn_2,
        replacement_journal_dict=replacement_journal,
        replacement_challan_dict=challan,
        reason="Corrected rate per negotiated discount",
        actor="CONTROLLER_USER"
    )

    # Verify audit lineage links
    orig_2_after = store.get_general_ledger(orig_txn_2)
    assert orig_2_after["status"] == "REVERSED"
    assert orig_2_after["reversal_entry_id"] == f"REV-{orig_txn_2}"
    assert orig_2_after["replacement_entry_id"] == "GL-REPLACEMENT-02"

    assert rep_p2["journal"]["original_entry_id"] == orig_txn_2
    assert rep_p2["journal"]["reversal_entry_id"] == f"REV-{orig_txn_2}"
    assert rep_p2["status"] == "ACTIVE"


# ============================================================================
# TEST 10: Dynamic Discounting Simple vs Effective Yield
# ============================================================================
def test_dynamic_discounting_simple_vs_effective_yield():
    """Verifies mathematical distinction between simple APR (36.5%) and compounded EAR (44.59%), with explainability."""
    gross = Decimal("200000.00")
    inv_date = date.today().isoformat()

    # Case A: Standard 2/10 Net 30 with no hurdle rate provided
    sched = WorkingCapitalScheduler.schedule_payment_terms(
        invoice_date_str=inv_date,
        gross_amount=gross,
        terms_type=PaymentTermsType.DISCOUNT_2_10_NET_30
    )
    assert sched.discount_rate_pct == 2.0
    assert sched.potential_discount_savings == Decimal("4000.00")
    assert sched.simple_annualized_return_pct == 36.5
    assert sched.effective_annualized_return_pct == 44.59
    assert sched.annualized_treasury_yield_pct == 36.5  # backwards compatibility
    assert sched.recommendation == "TAKE_EARLY_DISCOUNT"

    # Case B: Corporate cost of capital is 12.0% (< 36.5% yield) -> TAKE_EARLY_DISCOUNT
    sched_attractive = WorkingCapitalScheduler.schedule_payment_terms(
        invoice_date_str=inv_date,
        gross_amount=gross,
        terms_type=PaymentTermsType.DISCOUNT_2_10_NET_30,
        cost_of_capital_pct=12.0,
        liquidity_cost_pct=1.5  # Total hurdle = 13.5%
    )
    assert sched_attractive.recommendation == "TAKE_EARLY_DISCOUNT"
    assert sched_attractive.net_economic_benefit > Decimal("0.00")
    assert "exceeds hurdle rate" in sched_attractive.explanation

    # Case C: High borrowing cost / emergency liquidity hurdle 40.0% (> 36.5% yield) -> HOLD_CASH_FULL_TERM
    sched_expensive = WorkingCapitalScheduler.schedule_payment_terms(
        invoice_date_str=inv_date,
        gross_amount=gross,
        terms_type=PaymentTermsType.DISCOUNT_2_10_NET_30,
        cost_of_capital_pct=38.0,
        liquidity_cost_pct=5.0  # Total hurdle = 43.0%
    )
    assert sched_expensive.recommendation == "HOLD_CASH_FULL_TERM"
    assert sched_expensive.net_economic_benefit <= Decimal("0.00")
    assert "exceeds or eliminates net benefit" in sched_expensive.explanation
