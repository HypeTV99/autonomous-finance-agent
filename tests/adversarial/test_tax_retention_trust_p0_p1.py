from decimal import Decimal
from datetime import datetime, timezone
import pytest
import uuid

from firestore_store import FirestoreStateStore
from razorpayx_client import RazorpayXBankingClient
from schemas import (
    FinancialPosition,
    GSTR2BStatus,
    PennyDropStatus,
    PennyDropVerification,
    RetentionLifecycleState,
    RetentionRecord,
    SystemEnvironment,
    TDSSection,
)
from services.tax_gstr2b import GSTR2BSplitSettlementEngine, SplitSettlementResult
from services.penny_drop import PennyDropValidationEngine
from services.payment_orchestrator import PaymentOrchestrator, PaymentOrchestrationError


@pytest.fixture
def store():
    return FirestoreStateStore()


@pytest.fixture
def mock_client():
    return RazorpayXBankingClient(
        api_key="rzp_test_mock",
        api_secret="mock_secret_123",
        account_number="23232300411222"
    )


def test_financial_position_conservation_invariant():
    """
    Test 1: Mathematical Financial Position Domain Separation (Prompt 7 Invariant 1).
    Conservation: immediate_payment_amount + tds_amount + credit_amount + contractual_retention_amount == gross_invoice_amount.
    """
    subtotal = Decimal("100000.00")
    gst = Decimal("18000.00")
    tds = Decimal("2000.00")
    credits = Decimal("5000.00")

    # Scenario A: GSTR-2B Pending -> GST retained in escrow
    res_pending = GSTR2BSplitSettlementEngine.calculate_split_settlement(
        subtotal=subtotal,
        gst_amount=gst,
        tds_amount=tds,
        credits_applied=credits,
        gstr2b_status=GSTR2BStatus.PENDING_SUPPLIER_FILING,
        contract_permits_retention=True
    )
    pos = res_pending.financial_position
    assert pos is not None
    assert pos.gross_invoice_amount == Decimal("118000.00")
    assert pos.base_amount == Decimal("100000.00")
    assert pos.gst_amount == Decimal("18000.00")
    assert pos.tds_amount == Decimal("2000.00")
    assert pos.credit_amount == Decimal("5000.00")
    assert pos.contractual_retention_amount == Decimal("18000.00")
    assert pos.immediate_payment_amount == Decimal("93000.00")  # 100,000 - 2,000 - 5,000
    assert pos.immediate_payment_amount + pos.tds_amount + pos.credit_amount + pos.contractual_retention_amount == pos.gross_invoice_amount

    # Scenario B: GSTR-2B Matched -> 0 retention, full payout less TDS and credit
    res_matched = GSTR2BSplitSettlementEngine.calculate_split_settlement(
        subtotal=subtotal,
        gst_amount=gst,
        tds_amount=tds,
        credits_applied=credits,
        gstr2b_status=GSTR2BStatus.MATCHED,
        contract_permits_retention=True
    )
    pos_m = res_matched.financial_position
    assert pos_m is not None
    assert pos_m.contractual_retention_amount == Decimal("0.00")
    assert pos_m.immediate_payment_amount == Decimal("111000.00")  # 118,000 - 2,000 - 5,000
    assert pos_m.immediate_payment_amount + pos_m.tds_amount + pos_m.credit_amount + pos_m.contractual_retention_amount == pos_m.gross_invoice_amount


def test_financial_position_violation_raises():
    """
    Test 2: Mathematical Conservation Validator strictly rejects corrupted or leaked amounts.
    """
    with pytest.raises(ValueError, match="Financial position conservation violated"):
        FinancialPosition(
            gross_invoice_amount=Decimal("118000.00"),
            base_amount=Decimal("100000.00"),
            gst_amount=Decimal("18000.00"),
            tds_amount=Decimal("2000.00"),
            credit_amount=Decimal("0.00"),
            contractual_retention_amount=Decimal("18000.00"),
            immediate_payment_amount=Decimal("99000.00")  # Corrupted: 99,000 + 2,000 + 18,000 = 119,000 != 118,000
        )


def test_all_fourteen_gstr2b_states_handled():
    """
    Test 3: Verify all 14 statutory GSTR-2B states are handled appropriately.
    MATCHED and MATCHED_IN_2B release GST immediately; all mismatch/pending states hold GST in escrow.
    """
    subtotal = Decimal("50000.00")
    gst = Decimal("9000.00")
    tds = Decimal("1000.00")

    matched_states = [GSTR2BStatus.MATCHED, GSTR2BStatus.MATCHED_IN_2B]
    non_matched_states = [
        GSTR2BStatus.PENDING,
        GSTR2BStatus.NOT_FILED,
        GSTR2BStatus.PARTIALLY_MATCHED,
        GSTR2BStatus.TAX_AMOUNT_MISMATCH,
        GSTR2BStatus.TAXABLE_VALUE_MISMATCH,
        GSTR2BStatus.GSTIN_MISMATCH,
        GSTR2BStatus.INVOICE_REFERENCE_MISMATCH,
        GSTR2BStatus.AMENDED,
        GSTR2BStatus.CREDIT_NOTE_APPLIED,
        GSTR2BStatus.DISPUTED,
        GSTR2BStatus.TIMEOUT,
        GSTR2BStatus.MANUAL_REVIEW,
        GSTR2BStatus.ITC_INELIGIBLE,
        GSTR2BStatus.PENDING_SUPPLIER_FILING,
    ]

    for state in matched_states:
        res = GSTR2BSplitSettlementEngine.calculate_split_settlement(
            subtotal=subtotal, gst_amount=gst, tds_amount=tds, gstr2b_status=state
        )
        assert res.gst_retention_escrow == Decimal("0.00"), f"State {state} should not retain GST"
        assert res.settlement_status == "FULL_CLEARANCE_ITC_GUARANTEED"
        assert res.retention_record is None

    for state in non_matched_states:
        res = GSTR2BSplitSettlementEngine.calculate_split_settlement(
            subtotal=subtotal, gst_amount=gst, tds_amount=tds, gstr2b_status=state
        )
        assert res.gst_retention_escrow == gst, f"State {state} must retain GST"
        assert res.settlement_status == "SPLIT_SETTLEMENT_GST_HELD"
        assert res.retention_record is not None
        assert res.retention_record.remaining_amount == gst


def test_contract_prohibits_retention():
    """
    Test 4: Commercial Contract Safeguard:
    If contract does not authorize retention (contract_permits_retention=False),
    GST CANNOT be held in escrow even if GSTR-2B is pending.
    """
    subtotal = Decimal("100000.00")
    gst = Decimal("18000.00")
    tds = Decimal("2000.00")

    res = GSTR2BSplitSettlementEngine.calculate_split_settlement(
        subtotal=subtotal,
        gst_amount=gst,
        tds_amount=tds,
        gstr2b_status=GSTR2BStatus.PENDING,
        contract_permits_retention=False
    )
    assert res.gst_retention_escrow == Decimal("0.00")
    assert res.immediate_base_disbursal == Decimal("116000.00")  # 118,000 - 2,000
    assert res.settlement_status == "CONTRACT_PROHIBITS_RETENTION_FULL_DISBURSED"
    assert res.retention_record is None


def test_idempotent_retention_full_release(store):
    """
    Test 5: Retention Release Idempotency (Prompt 7 Rule 4):
    Duplicate release calls must not release funds twice or corrupt ledger.
    """
    subtotal = Decimal("100000.00")
    gst = Decimal("18000.00")
    tds = Decimal("2000.00")
    inv_no = f"INV-RET-IDEM-{uuid.uuid4().hex[:6]}"

    res = GSTR2BSplitSettlementEngine.calculate_split_settlement(
        subtotal=subtotal,
        gst_amount=gst,
        tds_amount=tds,
        invoice_number=inv_no,
        vendor_id="VEND-IDEM",
        store=store
    )
    assert res.retention_record is not None
    ret_id = res.retention_record.retention_id

    # 1. First full release
    ok1, rec1, msg1 = GSTR2BSplitSettlementEngine.release_retention(
        retention_id=ret_id,
        evidence_reference="GSTR-2B-OCT2026-UPLOAD",
        store=store
    )
    assert ok1 is True
    assert rec1 is not None
    assert rec1.state == RetentionLifecycleState.RELEASED
    assert rec1.released_amount == Decimal("18000.00")
    assert rec1.remaining_amount == Decimal("0.00")
    assert len(rec1.release_history) == 1

    # 2. Duplicate release attempt
    ok2, rec2, msg2 = GSTR2BSplitSettlementEngine.release_retention(
        retention_id=ret_id,
        evidence_reference="DUPLICATE_CALL",
        store=store
    )
    assert ok2 is True
    assert "already fully released" in msg2.lower() or "idempotent" in msg2.lower()
    assert rec2.released_amount == Decimal("18000.00")  # Did NOT double to 36,000
    assert len(rec2.release_history) == 1  # No duplicate release entry


def test_partial_retention_release(store):
    """
    Test 6: Partial Retention Releases:
    Allow partial evidence releases while keeping track of remaining escrow balance.
    """
    subtotal = Decimal("100000.00")
    gst = Decimal("18000.00")
    tds = Decimal("2000.00")
    inv_no = f"INV-RET-PART-{uuid.uuid4().hex[:6]}"

    res = GSTR2BSplitSettlementEngine.calculate_split_settlement(
        subtotal=subtotal,
        gst_amount=gst,
        tds_amount=tds,
        invoice_number=inv_no,
        vendor_id="VEND-PART",
        store=store
    )
    ret_id = res.retention_record.retention_id

    # Release 1: ₹10,000 of ₹18,000
    ok1, rec1, _ = GSTR2BSplitSettlementEngine.release_retention(
        retention_id=ret_id,
        release_amount=Decimal("10000.00"),
        evidence_reference="PARTIAL_GSTR1_REC",
        store=store
    )
    assert ok1 is True
    assert rec1.state == RetentionLifecycleState.PARTIAL_RELEASE
    assert rec1.released_amount == Decimal("10000.00")
    assert rec1.remaining_amount == Decimal("8000.00")

    # Release 2: Remaining ₹8,000
    ok2, rec2, _ = GSTR2BSplitSettlementEngine.release_retention(
        retention_id=ret_id,
        release_amount=Decimal("8000.00"),
        evidence_reference="FINAL_GSTR1_REC",
        store=store
    )
    assert ok2 is True
    assert rec2.state == RetentionLifecycleState.RELEASED
    assert rec2.released_amount == Decimal("18000.00")
    assert rec2.remaining_amount == Decimal("0.00")
    assert len(rec2.release_history) == 2


def test_disputed_retention_blocks_release(store):
    """
    Test 7: Retention Governance:
    Disputed retentions cannot be released until dispute resolution.
    """
    inv_no = f"INV-RET-DISP-{uuid.uuid4().hex[:6]}"
    res = GSTR2BSplitSettlementEngine.calculate_split_settlement(
        subtotal=Decimal("50000.00"),
        gst_amount=Decimal("9000.00"),
        tds_amount=Decimal("1000.00"),
        invoice_number=inv_no,
        vendor_id="VEND-DISP",
        store=store
    )
    ret_id = res.retention_record.retention_id

    # Transition to DISPUTED
    store.update_retention_record(ret_id, {"state": RetentionLifecycleState.DISPUTED.value})

    # Attempt release
    ok, rec, msg = GSTR2BSplitSettlementEngine.release_retention(
        retention_id=ret_id,
        store=store
    )
    assert ok is False
    assert "DISPUTED" in msg
    assert rec.remaining_amount == Decimal("9000.00")


def test_production_payment_blocked_without_production_trust(store, mock_client):
    """
    Test 8: Production Payout Gating (Prompt 7 Rule 6):
    Real/Production payments strictly require PRODUCTION_TRUST bank verification evidence.
    Simulation or Sandbox evidence cannot authorize live production disbursals.
    """
    orchestrator = PaymentOrchestrator(store=store, banking_client=mock_client)
    inv_no = f"INV-PROD-GATE-{uuid.uuid4().hex[:6]}"

    intent, _ = orchestrator.get_or_create_payment_intent(
        invoice_number=inv_no,
        vendor_id="VEND-PROD-1",
        vendor_pan="AAACA1234T",
        fiscal_year="2026-27",
        fund_account_id="fa_prod_001",
        gross_subtotal=Decimal("100000.00"),
        tax_amount=Decimal("18000.00"),
        tds_withheld=Decimal("2000.00"),
        tds_section=TDSSection.SECTION_194C_CORP,
        applied_credits=Decimal("0.00"),
        net_payout_amount=Decimal("116000.00"),
        environment="PRODUCTION",
        bank_verification_trust="SANDBOX_TRUST"  # Sandbox trust injected into Production intent
    )

    with pytest.raises(PaymentOrchestrationError, match="Production Payout Gated"):
        orchestrator.dispatch_payment_intent(intent, mock_client)


def test_production_payment_allowed_with_audited_override(store, mock_client):
    """
    Test 9: Production Payout with Audited Manual Override (Prompt 7 Rule 6):
    A valid audited manual override (e.g. approved_by CFO) unblocks production payout.
    """
    orchestrator = PaymentOrchestrator(store=store, banking_client=mock_client)
    inv_no = f"INV-PROD-OVR-{uuid.uuid4().hex[:6]}"

    intent, _ = orchestrator.get_or_create_payment_intent(
        invoice_number=inv_no,
        vendor_id="VEND-PROD-2",
        vendor_pan="AAACA1234T",
        fiscal_year="2026-27",
        fund_account_id="fa_prod_002",
        gross_subtotal=Decimal("100000.00"),
        tax_amount=Decimal("18000.00"),
        tds_withheld=Decimal("2000.00"),
        tds_section=TDSSection.SECTION_194C_CORP,
        applied_credits=Decimal("0.00"),
        net_payout_amount=Decimal("116000.00"),
        environment="PRODUCTION",
        bank_verification_trust="REQUIRES_REVIEW",
        manual_override={
            "approved_by": "FIN_CONTROLLER",
            "reason": "Direct bank manager confirmation obtained"
        }
    )

    res = orchestrator.dispatch_payment_intent(intent, mock_client)
    assert res["status"] == "SUCCESS"
    assert res["state"] == "SETTLED"
    assert res["payout_id"] is not None


def test_simulation_reference_namespacing_and_multisignal_identity():
    """
    Test 10: Environment Isolation & Multi-Signal Identity Proof:
    - Simulation references strictly use SIM-... namespace.
    - High fuzzy match without approved master yields MANUAL_REVIEW instead of AUTO_APPROVE.
    - Bank cooling flag immediately triggers BLOCK.
    """
    # 1. Simulation Namespacing
    sim_verif = PennyDropValidationEngine.verify_beneficiary_account(
        account_number="50200084924021",
        ifsc="HDFC0000060",
        vendor_legal_name="Alpha Tech Labs Pvt Ltd",
        vendor_pan="AAACA1234T",
        environment="SIMULATION"
    )
    assert sim_verif.transfer_reference_id.startswith("SIM-NPCI-")
    assert sim_verif.provider_reference.startswith("SIM-NPCI-")
    assert sim_verif.environment == "SIMULATION"

    # 2. Multi-Signal Identity: Fuzzy match without approved master status yields MANUAL_REVIEW
    review_verif = PennyDropValidationEngine.verify_beneficiary_account(
        account_number="50200084924021",
        ifsc="HDFC0000060",
        vendor_legal_name="Alpha Tech Labs Pvt Ltd",
        vendor_pan="AAACA1234T",
        environment="PRODUCTION",
        is_approved_master=False  # NOT in approved master registry
    )
    assert review_verif.pan_name_match_score_pct >= 80.0
    assert review_verif.outcome == "MANUAL_REVIEW"
    assert review_verif.status == PennyDropStatus.MANUAL_REVIEW_REQUIRED
    assert review_verif.trust_level == "REQUIRES_REVIEW"

    # 3. Bank Cooling Active -> Immediate BLOCK
    cooling_verif = PennyDropValidationEngine.verify_beneficiary_account(
        account_number="50200084924021",
        ifsc="HDFC0000060",
        vendor_legal_name="Alpha Tech Labs Pvt Ltd",
        vendor_pan="AAACA1234T",
        bank_cooling_active=True
    )
    assert cooling_verif.outcome == "BLOCK"
    assert cooling_verif.status == PennyDropStatus.FAILED
    assert cooling_verif.trust_level == "UNTRUSTED"
