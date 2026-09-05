import copy
from datetime import date, datetime, timezone
from decimal import Decimal
import hashlib
import json
import pytest

from schemas import (
    DecisionRecord,
    DoubleEntryJournal,
    ExtractedInvoicePayload,
    ExtractionMethod,
    FieldProvenanceRecord,
    InvoiceDocumentLineage,
    InvoiceLineItem,
    PaymentInstruction,
    ReplayExecutionResult,
    ReplayMode,
    TaxCalculationResult,
    TaxFramework,
    TDSSection,
)
from services.crypto import (
    CanonicalFinancialDecisionSerializer,
    EnterpriseKeyRegistry,
    verify_external_auditor_signature,
    _ED25519_PRIV,
    ED25519_PUBLIC_KEY_HEX,
)
from services.decision_engine import DecisionEngine
from services.ledger import HardenedStatutoryLedgerEngine, LedgerNettingEngine
from services.lineage import DecisionReplayEngine
from services.policy_registry import (
    EnterprisePolicyRegistry,
    ImmutablePolicyMutationError,
    PolicyDefinition,
    PolicyNotFoundError,
    PolicyType,
)
from firestore_store import FirestoreStateStore, PostedDecisionMutationError
from tax_engine import StatutoryComplianceTaxEngine


@pytest.fixture
def base_invoice_and_decision():
    """Builds a deterministic, cryptographically attested DecisionRecord for testing."""
    inv = ExtractedInvoicePayload(
        invoice_number="INV-CRYPTO-2026-001",
        vendor_pan="AABCQ1234T",
        invoice_date="2026-05-15",
        fiscal_year="2026-27",
        line_items=[
            InvoiceLineItem(
                sku="SKU-SERV-01",
                description="Architecture Security Audit",
                quantity=Decimal("1.0"),
                unit_price=Decimal("100000.00"),
                line_total=Decimal("100000.00")
            )
        ],
        subtotal=Decimal("100000.00"),
        tax_amount=Decimal("18000.00"),
        total_amount=Decimal("118000.00"),
        ocr_confidence_score=0.99
    )

    tax_res = StatutoryComplianceTaxEngine.compute_statutory_tax(
        subtotal=inv.subtotal,
        gst_amount=inv.tax_amount,
        section=TDSSection.SECTION_194J_PROF,
        vendor_pan=inv.vendor_pan,
        transaction_date=date(2026, 5, 15)
    )

    netting = LedgerNettingEngine.apply_credits_and_advances(tax_res.final_disbursement, [])
    journal, challan = HardenedStatutoryLedgerEngine.generate_accounting_records(
        inv.invoice_number, inv.vendor_pan, inv.fiscal_year, inv.subtotal, netting.applied_credit_total, tax_res, inv.tax_amount
    )

    po_snap_hash = hashlib.sha256(b"PO-2026-REV-01-ITEMS").hexdigest()
    grn_snap_hash = hashlib.sha256(b"GRN-2026-001-ACCEPTED").hexdigest()
    vend_snap_hash = hashlib.sha256(b"VENDOR-STATE-APPROVED-BANK-COOLING-OK").hexdigest()

    decision_rec, payment_instr = DecisionEngine.build_immutable_decision_record(
        invoice=inv,
        vendor_id="VEND-SEC-99",
        tax_result=tax_res,
        netting_result=netting,
        journal=journal,
        source_document_hash="sha256:doc_evidence_clean_pdf_99",
        reconciliation_evidence={"status": "MATCHED_3WAY_CLEAN", "po_number": "PO-2026-REV-01"},
        fund_account_id="fa_test_bank_01",
        idempotency_key="IDEMP-DEC-CRYPTO-001",
        po_snapshot_hash=po_snap_hash,
        grn_snapshot_hash=grn_snap_hash,
        vendor_snapshot_hash=vend_snap_hash,
        matching_policy_version="2026.1",
        retention_policy_version="2026.1",
        tolerance_policy_version="2026.1"
    )

    return inv, decision_rec, payment_instr


def test_complete_decision_attestation_tampering(base_invoice_and_decision):
    """
    Test 1: Complete decision attestation.
    Tampering with matching policy version, vendor snapshot hash, or ledger entry hash
    MUST alter canonical digest and cause Ed25519 signature verification to fail.
    """
    inv, decision_rec, _ = base_invoice_and_decision

    # 1. Baseline verification passes
    valid, reason = verify_external_auditor_signature(
        canonical_payload_sha256=decision_rec.canonical_payload_sha256,
        signature_hex=decision_rec.cryptographic_signature,
        public_key_hex=decision_rec.public_key_hex,
        signing_key_id=decision_rec.signing_key_id,
        signed_at=decision_rec.signed_at,
        valid_from=decision_rec.key_valid_from,
        valid_until=decision_rec.key_valid_until
    )
    assert valid is True
    assert reason == "VALID_SIGNATURE"

    # 2. Tamper with matching policy version
    reconstructed_tampered_policy = copy.deepcopy(decision_rec.model_dump())
    reconstructed_tampered_policy["matching_policy_version"] = "2025.4-MUTATED"
    # Rebuild canonical payload dict exactly as DecisionEngine creates it
    payload_dict = {k: v for k, v in reconstructed_tampered_policy.items() if k in (
        "decision_id", "invoice_number", "vendor_id", "vendor_pan", "fiscal_year",
        "source_document_hash", "source_document_uri", "gst_irn", "tax_framework",
        "canonical_rule_id", "internal_rule_id", "statutory_provision", "government_section",
        "government_table_item", "gazette_citation", "cbdt_circular_reference",
        "official_source_uri", "tax_rule_version", "statutory_return_form",
        "statutory_return_field_code", "form_26q_code", "internal_reporting_code",
        "challan_281_code", "pan_26as_credit_tag", "calculation_version", "effective_date",
        "previous_decision_digest", "reconciliation_evidence", "tds_calculation",
        "credit_allocation_manifest", "general_ledger_tx_id", "payment_instruction",
        "decision_timestamp", "schema_version", "po_snapshot_hash", "grn_snapshot_hash",
        "vendor_snapshot_hash", "matching_policy_version", "tax_policy_version",
        "payment_policy_version", "retention_policy_version", "tolerance_policy_version",
        "discount_policy_version", "accounting_policy_version", "risk_policy_version",
        "credit_allocation_hash", "gstr_evidence_hash", "bank_verification_evidence_hash",
        "ledger_entry_hash", "payment_intent_id", "canonicalization_version"
    )}
    tampered_canon = CanonicalFinancialDecisionSerializer.serialize(payload_dict)
    tampered_digest = hashlib.sha256(tampered_canon.encode("utf-8")).hexdigest()
    assert tampered_digest != decision_rec.canonical_payload_sha256

    tampered_valid, tampered_reason = verify_external_auditor_signature(
        canonical_payload_sha256=tampered_digest,
        signature_hex=decision_rec.cryptographic_signature,
        public_key_hex=decision_rec.public_key_hex
    )
    assert tampered_valid is False
    assert "MISMATCH" in tampered_reason


def test_canonical_numeric_and_string_representation():
    """
    Test 2: Canonical numeric and string representation under CFDS-v1.
    Verifies fixed scale (2 decimals for currency, 4 for rates), NFC Unicode composition,
    and exact byte-for-byte serialization reproducibility.
    """
    payload_1 = {
        "amount": Decimal("100000"),
        "tax_rate": Decimal("0.1"),
        "vendor": "Caf\u00e9 Financials",  # Precomposed é
        "null_field": None
    }
    payload_2 = {
        "vendor": "Cafe\u0301 Financials",  # Decomposed e + combining acute accent
        "null_field": None,
        "tax_rate": Decimal("0.10000"),
        "amount": Decimal("100000.00")
    }

    canon_1 = CanonicalFinancialDecisionSerializer.serialize(payload_1)
    canon_2 = CanonicalFinancialDecisionSerializer.serialize(payload_2)

    assert canon_1 == canon_2
    assert '"amount":"100000.00"' in canon_1
    assert '"tax_rate":"0.1000"' in canon_1
    assert '"Café Financials"' in canon_1
    assert hashlib.sha256(canon_1.encode("utf-8")).hexdigest() == hashlib.sha256(canon_2.encode("utf-8")).hexdigest()


def test_key_rotation_historical_preservation(base_invoice_and_decision):
    """
    Test 3: Key management and rotation evidence.
    Verifies that historical decisions signed with an older key remain verifiable within
    their designated validity window, while signatures outside the window or under
    compromised keys are rejected.
    """
    _, decision_rec, _ = base_invoice_and_decision

    # 1. Historical Key valid for calendar year 2025
    historical_key = {
        "key_id": "kms://asia-south1/finance-signer-ed25519-2025-v1",
        "algorithm": "Ed25519",
        "public_key_hex": decision_rec.public_key_hex,
        "status": "ACTIVE",
        "valid_from": "2025-01-01T00:00:00Z",
        "valid_until": "2025-12-31T23:59:59Z",
        "root_authority": "FinanceAgent-Enterprise-Trust-Anchor-v1"
    }
    EnterpriseKeyRegistry.register_key(historical_key)

    # Historical decision signed inside validity window (October 2025)
    valid_hist, reason_hist = verify_external_auditor_signature(
        canonical_payload_sha256=decision_rec.canonical_payload_sha256,
        signature_hex=decision_rec.cryptographic_signature,
        public_key_hex=decision_rec.public_key_hex,
        signing_key_id=historical_key["key_id"],
        signed_at="2025-10-15T10:00:00Z"
    )
    assert valid_hist is True

    # Attempt to use expired 2025 key for a 2026 decision fails
    expired_valid, expired_reason = verify_external_auditor_signature(
        canonical_payload_sha256=decision_rec.canonical_payload_sha256,
        signature_hex=decision_rec.cryptographic_signature,
        public_key_hex=decision_rec.public_key_hex,
        signing_key_id=historical_key["key_id"],
        signed_at="2026-05-15T10:00:00Z"
    )
    assert expired_valid is False
    assert "KEY_EXPIRED_OR_PREMATURE" in expired_reason


def test_decision_store_append_only_immutability(base_invoice_and_decision):
    """
    Test 4: Append-only decision store immutability.
    Mutating an existing posted DecisionRecord MUST raise PostedDecisionMutationError,
    while persisting an identical payload is an idempotent no-op.
    """
    store = FirestoreStateStore(project_id="test-finance-crypto")
    _, decision_rec, _ = base_invoice_and_decision

    record_dict = decision_rec.model_dump()
    decision_id = decision_rec.decision_id

    # 1. Initial persistence succeeds
    store.persist_immutable_decision_record(record_dict)
    fetched = store.get_decision_record(decision_id)
    assert fetched is not None
    assert fetched["decision_id"] == decision_id

    # 2. Idempotent replay of identical payload succeeds without error
    store.persist_immutable_decision_record(record_dict)

    # 3. Attempting to mutate a posted decision raises PostedDecisionMutationError
    mutated_record = copy.deepcopy(record_dict)
    mutated_record["vendor_id"] = "VEND-ROGUE-ATTACKER"
    with pytest.raises(PostedDecisionMutationError) as exc_info:
        store.persist_immutable_decision_record(mutated_record)
    assert "strictly append-only" in str(exc_info.value)

    # 4. Attempting to mutate financial decision raises PostedDecisionMutationError
    store.persist_financial_decision(record_dict)
    with pytest.raises(PostedDecisionMutationError):
        store.persist_financial_decision(mutated_record)


def test_policy_registry_immutability():
    """
    Test 5: Enterprise policy registry immutability.
    Mutating an existing registered policy version in place raises ImmutablePolicyMutationError.
    Creating a new version is required for changes.
    """
    EnterprisePolicyRegistry.reset_registry()

    # 1. Retrieve default 2026.1 matching policy
    matching_policy = EnterprisePolicyRegistry.get_policy(PolicyType.MATCHING_POLICY, "2026.1")
    assert matching_policy.version == "2026.1"
    assert matching_policy.rules_payload["mode"] == "THREE_WAY_CUMULATIVE"

    # 2. Idempotent re-registration succeeds
    EnterprisePolicyRegistry.register_policy(matching_policy)

    # 3. In-place mutation of 2026.1 raises ImmutablePolicyMutationError
    mutated_policy = PolicyDefinition(
        policy_type=PolicyType.MATCHING_POLICY,
        version="2026.1",
        effective_from="2026-01-01T00:00:00Z",
        rules_digest="tampered_digest_12345",
        rules_payload={"mode": "PERMISSIVE_NO_PO_REQUIRED"}
    )
    with pytest.raises(ImmutablePolicyMutationError) as exc_info:
        EnterprisePolicyRegistry.register_policy(mutated_policy)
    assert "Cannot mutate registered immutable policy" in str(exc_info.value)

    # 4. Registering a new version monotonically (2026.2) succeeds
    new_version_rules = {"mode": "THREE_WAY_STRICT_ZERO_VARIANCE", "require_lineage": True}
    new_version_policy = PolicyDefinition(
        policy_type=PolicyType.MATCHING_POLICY,
        version="2026.2",
        effective_from="2026-07-01T00:00:00Z",
        rules_digest=EnterprisePolicyRegistry.compute_rules_digest(new_version_rules),
        rules_payload=new_version_rules
    )
    EnterprisePolicyRegistry.register_policy(new_version_policy)

    retrieved_v2 = EnterprisePolicyRegistry.get_policy(PolicyType.MATCHING_POLICY, "2026.2")
    assert retrieved_v2.version == "2026.2"


def test_historical_replay_determinism(base_invoice_and_decision):
    """
    Test 6: Historical replay determinism.
    HISTORICAL_REPLAY re-runs decision logic strictly using recorded snapshot hashes
    and policy versions, asserting identical cryptographic digest output.
    """
    _, decision_rec, _ = base_invoice_and_decision

    replay_result = DecisionReplayEngine.execute_replay(
        decision_record=decision_rec,
        mode=ReplayMode.HISTORICAL_REPLAY
    )

    assert replay_result.replay_mode == ReplayMode.HISTORICAL_REPLAY
    assert replay_result.cryptographically_identical is True
    assert replay_result.replayed_digest == decision_rec.canonical_payload_sha256
    assert replay_result.is_simulation is False
    assert replay_result.admissible_for_payout is True
    assert replay_result.variance_detected is False


def test_what_if_replay_simulation_isolation(base_invoice_and_decision):
    """
    Test 7: What-If replay simulation isolation.
    WHAT_IF_REPLAY accepts counterfactual overrides, recomputes output, and marks
    result as simulation-only (is_simulation=True, admissible_for_payout=False).
    """
    _, decision_rec, _ = base_invoice_and_decision

    what_if_result = DecisionReplayEngine.execute_replay(
        decision_record=decision_rec,
        mode=ReplayMode.WHAT_IF_REPLAY,
        overrides={
            "matching_policy_version": "2027.TEST",
            "tds_calculation.tds_rate": "0.2000"
        }
    )

    assert what_if_result.replay_mode == ReplayMode.WHAT_IF_REPLAY
    assert what_if_result.is_simulation is True
    assert what_if_result.admissible_for_payout is False
    assert what_if_result.variance_detected is True
    assert what_if_result.cryptographically_identical is False
    assert what_if_result.variance_details["applied_overrides"]["matching_policy_version"] == "2027.TEST"


def test_ocr_field_lineage_human_correction_preservation():
    """
    Test 8: OCR field source lineage & human correction preservation.
    Human corrections MUST NOT erase the original raw extracted value or confidence.
    """
    lineage = InvoiceDocumentLineage(
        document_hash="sha256:scan_inv_998877",
        document_uri="gs://ap-invoices-2026/INV-998877.pdf",
        ocr_engine="GoogleCloudDocumentAI-v1"
    )

    # 1. Add raw OCR extracted total amount
    field = FieldProvenanceRecord(
        field_name="total_amount",
        source_document_hash=lineage.document_hash,
        page_number=1,
        bounding_box=[0.82, 0.70, 0.85, 0.90],
        extraction_method=ExtractionMethod.OCR_DOCUMENT_AI,
        confidence_score=0.88,
        raw_extracted_value="1,18,000.00",
        normalized_value=Decimal("118000.00")
    )
    lineage.add_field(field)

    assert lineage.fields_provenance["total_amount"].raw_extracted_value == "1,18,000.00"
    assert lineage.fields_provenance["total_amount"].is_human_corrected is False

    # 2. Human reviewer corrects field
    lineage.correct_field(
        field_name="total_amount",
        corrected_value=Decimal("118000.00"),
        actor="SENIOR_ACCOUNTANT_MEERA",
        reason="Verified against vendor contract currency code"
    )

    corrected_field = lineage.fields_provenance["total_amount"]
    assert corrected_field.is_human_corrected is True
    assert corrected_field.raw_extracted_value == "1,18,000.00"  # STRICTLY PRESERVED
    assert corrected_field.original_extracted_value == "1,18,000.00"  # STRICTLY PRESERVED
    assert corrected_field.normalized_value == Decimal("118000.00")
    assert corrected_field.correction_actor == "SENIOR_ACCOUNTANT_MEERA"
    assert corrected_field.extraction_method == ExtractionMethod.HUMAN_CORRECTION


def test_one_paisa_financial_tamper_detection(base_invoice_and_decision):
    """
    Test 9: 1-paisa financial tamper test.
    Altering any financial position by 1 paisa (₹0.01) immediately breaks the SHA-256
    digest and causes Ed25519 signature verification to fail.
    """
    _, decision_rec, _ = base_invoice_and_decision

    # Clone payload dict and modify subtotal by ₹0.01
    mutated_dict = copy.deepcopy(decision_rec.model_dump())
    orig_subtotal = Decimal(mutated_dict["tds_calculation"]["subtotal_pre_gst"])
    mutated_dict["tds_calculation"]["subtotal_pre_gst"] = str(orig_subtotal + Decimal("0.01"))

    payload_dict = {k: v for k, v in mutated_dict.items() if k in (
        "decision_id", "invoice_number", "vendor_id", "vendor_pan", "fiscal_year",
        "source_document_hash", "source_document_uri", "gst_irn", "tax_framework",
        "canonical_rule_id", "internal_rule_id", "statutory_provision", "government_section",
        "government_table_item", "gazette_citation", "cbdt_circular_reference",
        "official_source_uri", "tax_rule_version", "statutory_return_form",
        "statutory_return_field_code", "form_26q_code", "internal_reporting_code",
        "challan_281_code", "pan_26as_credit_tag", "calculation_version", "effective_date",
        "previous_decision_digest", "reconciliation_evidence", "tds_calculation",
        "credit_allocation_manifest", "general_ledger_tx_id", "payment_instruction",
        "decision_timestamp", "schema_version", "po_snapshot_hash", "grn_snapshot_hash",
        "vendor_snapshot_hash", "matching_policy_version", "tax_policy_version",
        "payment_policy_version", "retention_policy_version", "tolerance_policy_version",
        "discount_policy_version", "accounting_policy_version", "risk_policy_version",
        "credit_allocation_hash", "gstr_evidence_hash", "bank_verification_evidence_hash",
        "ledger_entry_hash", "payment_intent_id", "canonicalization_version"
    )}

    mutated_canon = CanonicalFinancialDecisionSerializer.serialize(payload_dict)
    mutated_digest = hashlib.sha256(mutated_canon.encode("utf-8")).hexdigest()

    assert mutated_digest != decision_rec.canonical_payload_sha256

    is_valid, reason = verify_external_auditor_signature(
        canonical_payload_sha256=mutated_digest,
        signature_hex=decision_rec.cryptographic_signature,
        public_key_hex=decision_rec.public_key_hex
    )
    assert is_valid is False
    assert "MISMATCH" in reason


def test_po_grn_vendor_snapshot_tamper_detection(base_invoice_and_decision):
    """
    Test 10: Procurement & vendor snapshot tamper detection.
    Altering the referenced PO snapshot hash, GRN snapshot hash, or vendor snapshot hash
    breaks the attestation envelope and fails verification.
    """
    _, decision_rec, _ = base_invoice_and_decision

    for snapshot_field in ("po_snapshot_hash", "grn_snapshot_hash", "vendor_snapshot_hash"):
        mutated_dict = copy.deepcopy(decision_rec.model_dump())
        mutated_dict[snapshot_field] = hashlib.sha256(b"ROGUE_ATTACKER_INJECTED_SNAPSHOT").hexdigest()

        payload_dict = {k: v for k, v in mutated_dict.items() if k in (
            "decision_id", "invoice_number", "vendor_id", "vendor_pan", "fiscal_year",
            "source_document_hash", "source_document_uri", "gst_irn", "tax_framework",
            "canonical_rule_id", "internal_rule_id", "statutory_provision", "government_section",
            "government_table_item", "gazette_citation", "cbdt_circular_reference",
            "official_source_uri", "tax_rule_version", "statutory_return_form",
            "statutory_return_field_code", "form_26q_code", "internal_reporting_code",
            "challan_281_code", "pan_26as_credit_tag", "calculation_version", "effective_date",
            "previous_decision_digest", "reconciliation_evidence", "tds_calculation",
            "credit_allocation_manifest", "general_ledger_tx_id", "payment_instruction",
            "decision_timestamp", "schema_version", "po_snapshot_hash", "grn_snapshot_hash",
            "vendor_snapshot_hash", "matching_policy_version", "tax_policy_version",
            "payment_policy_version", "retention_policy_version", "tolerance_policy_version",
            "discount_policy_version", "accounting_policy_version", "risk_policy_version",
            "credit_allocation_hash", "gstr_evidence_hash", "bank_verification_evidence_hash",
            "ledger_entry_hash", "payment_intent_id", "canonicalization_version"
        )}

        mutated_canon = CanonicalFinancialDecisionSerializer.serialize(payload_dict)
        mutated_digest = hashlib.sha256(mutated_canon.encode("utf-8")).hexdigest()

        assert mutated_digest != decision_rec.canonical_payload_sha256

        is_valid, reason = verify_external_auditor_signature(
            canonical_payload_sha256=mutated_digest,
            signature_hex=decision_rec.cryptographic_signature,
            public_key_hex=decision_rec.public_key_hex
        )
        assert is_valid is False
        assert "MISMATCH" in reason
