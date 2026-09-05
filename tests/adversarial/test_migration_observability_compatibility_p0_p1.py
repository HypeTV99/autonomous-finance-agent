"""
tests/adversarial/test_migration_observability_compatibility_p0_p1.py
Prompt 11 of 12: Backward Compatibility, Expand-and-Contract Migration,
Structured Observability with Credential Redaction, Canonical UTC Time Semantics,
and Fail-Safe Environment Hardening.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
import pytest
from typing import Any, Dict

from firestore_store import FirestoreStateStore
from schemas import (
    DecisionRecord,
    ManualOverrideRecord,
    OpenCreditRecord,
    OverrideScope,
    PaymentInstruction,
    PaymentState,
    SystemEnvironment,
    TDSSection,
    normalize_environment,
)
from services.migration_service import MigrationService
from services.observability import (
    HighRiskEvent,
    StructuredSecurityLogger,
    get_security_logger,
    mask_bank_account,
    sanitize_sensitive_data,
)
from services.override_governor import (
    NonOverridableInvariantViolationError,
    OverrideGovernor,
)
from services.payment_orchestrator import (
    PaymentOrchestrationError,
    PaymentOrchestrator,
)


# ==============================================================================
# TEST FIXTURES & HELPERS
# ==============================================================================

@pytest.fixture
def clean_store():
    """Provides an isolated in-memory FirestoreStateStore."""
    store = FirestoreStateStore()
    if store._is_mock:
        store._mock_db = {
            "distributed_locks": {},
            "processed_invoices": {},
            "po_consumption_ledger": {},
            "idempotency_records": {},
            "outbox_events": {},
            "payment_intents": {},
            "credit_notes": {},
            "general_ledger_journals": {},
            "decision_records": {},
            "webhook_events": {}
        }
    return store


@pytest.fixture
def clean_security_logger():
    """Provides a security logger with a clean in-memory audit trail buffer."""
    sec_logger = get_security_logger()
    sec_logger.clear_buffer()
    return sec_logger


# ==============================================================================
# 1. BACKWARD COMPATIBILITY & DUAL-READ ACCEPTANCE (Prompt 11 Rule 2)
# ==============================================================================

def test_legacy_payment_record_dual_read_compatibility():
    """
    Verifies that legacy payment payloads (from Prompts 1-3) missing new fields
    (e.g., payout_paise, requires_zero_payout_hold, financial_snapshot_hash)
    and using legacy alias keys (gross_amount, settlement_amount) parse seamlessly
    without raising ValidationError, and populate safe defaults.
    """
    legacy_payload = {
        "instruction_id": "INS-LEGACY-001",
        "invoice_number": "INV-2024-9988",
        "vendor_id": "VEND-LEGACY-01",
        "gross_amount": "50000.00",
        "settlement_amount": "49000.00",
        "status": "PENDING"
    }

    # Should succeed via the pre-validator adapter
    payment = PaymentInstruction.model_validate(legacy_payload)

    # Invariants
    assert payment.instruction_id == "INS-LEGACY-001"
    assert payment.invoice_number == "INV-2024-9988"
    assert payment.gross_subtotal == Decimal("50000.00")
    assert payment.net_payout_amount == Decimal("49000.00")
    assert payment.payout_paise == 4900000
    assert payment.requires_zero_payout_hold is False
    assert payment.environment == SystemEnvironment.SANDBOX.value
    assert payment.vendor_pan == "PANNOTPROVIDED"
    assert payment.currency == "INR"
    assert payment.status == PaymentState.PENDING

    # Compatibility properties
    assert payment.payment_intent_id == "INS-LEGACY-001"
    assert payment.invoice_id == "INV-2024-9988"
    assert payment.beneficiary_reference == payment.fund_account_id


def test_legacy_zero_payout_payment_dual_read():
    """
    Verifies that a 100% credit netted legacy payment automatically derives
    requires_zero_payout_hold=True and payout_paise=0.
    """
    zero_payout_legacy = {
        "instruction_id": "INS-ZERO-002",
        "invoice_number": "INV-NET-ZERO",
        "vendor_id": "VEND-CREDIT-01",
        "gross_amount": "10000.00",
        "settlement_amount": "0.00"
    }
    payment = PaymentInstruction.model_validate(zero_payout_legacy)
    assert payment.net_payout_amount == Decimal("0.00")
    assert payment.payout_paise == 0
    assert payment.requires_zero_payout_hold is True


def test_legacy_credit_record_dual_read_compatibility():
    """
    Verifies that legacy open credit records adapt cleanly, maintaining
    monetary conservation without dropping existing balances.
    """
    legacy_credit = {
        "credit_note_id": "CR-LEGACY-77",
        "vendor_id": "VEND-01",
        "original_amount": "15000.00",
        "available_amount": "15000.00"
    }
    credit = OpenCreditRecord.model_validate(legacy_credit)
    assert credit.original_amount == Decimal("15000.00")
    assert credit.available_amount == Decimal("15000.00")
    assert credit.consumed_amount == Decimal("0.00")
    assert credit.reserved_amount == Decimal("0.00")
    assert credit.current_balance == Decimal("15000.00")


def test_legacy_decision_record_preserves_historical_distinction():
    """
    Verifies that historical decision records missing modern policy versioning
    default to 'LEGACY_UNVERSIONED' and do not falsely claim modern 2026 policies.
    """
    legacy_decision = {
        "decision_id": "DEC-HISTORIC-101",
        "invoice_number": "INV-HISTORIC-101",
        "vendor_id": "VEND-HISTORIC",
        "vendor_pan": "AAACB1234K",
        "fiscal_year": "2024-25",
        "source_document_hash": "sha256_mock_hash_doc_historic",
        "signed_decision_digest": "sha256_mock_digest_historic"
    }
    decision = DecisionRecord.model_validate(legacy_decision)
    assert decision.matching_policy_version == "LEGACY_UNVERSIONED"
    assert decision.tax_policy_version == "LEGACY_UNVERSIONED"
    assert decision.payment_policy_version == "LEGACY_UNVERSIONED"
    assert decision.retention_policy_version == "LEGACY_UNVERSIONED"
    assert decision.tolerance_policy_version == "LEGACY_UNVERSIONED"
    assert decision.discount_policy_version == "LEGACY_UNVERSIONED"
    assert decision.accounting_policy_version == "LEGACY_UNVERSIONED"
    assert decision.risk_policy_version == "LEGACY_UNVERSIONED"


# ==============================================================================
# 2. EXPAND-AND-CONTRACT DATA MIGRATION (Prompt 11 Rule 3)
# ==============================================================================

def test_migration_service_idempotence(clean_store):
    """
    Verifies that MigrationService can be executed repeatedly on existing
    unmigrated and partially migrated records with strictly idempotent results.
    """
    migration_svc = MigrationService(clean_store)

    # Seed legacy payment intent in store
    legacy_intent = {
        "instruction_id": "INS-MIGRATE-01",
        "invoice_number": "INV-MIGRATE-01",
        "vendor_id": "VEND-01",
        "gross_amount": "25000.00",
        "settlement_amount": "24500.00",
        "idempotency_key": "idemp_mig_01",
        "status": "PENDING"
    }
    clean_store.save_payment_intent(legacy_intent)

    # Seed legacy credit note
    clean_store._mock_db.setdefault("vendor_open_credits", {})["VEND-01"] = [{
        "credit_note_id": "CR-MIGRATE-01",
        "vendor_id": "VEND-01",
        "original_amount": "5000.00",
        "available_amount": "5000.00"
    }]

    # Seed legacy decision
    clean_store._mock_db.setdefault("immutable_decision_records", {})["DEC-MIGRATE-01"] = {
        "decision_id": "DEC-MIGRATE-01",
        "invoice_number": "INV-MIGRATE-01",
        "vendor_id": "VEND-01",
        "fiscal_year": "2024-25"
    }

    # Run 1st migration pass
    stats_pass1 = migration_svc.run_full_migration()
    assert stats_pass1["payments_migrated"] == 1
    assert stats_pass1["credits_migrated"] == 1
    assert stats_pass1["decisions_migrated"] == 1

    migrated_intent = clean_store.get_payment_intent("idemp_mig_01")
    assert migrated_intent["schema_version"] == MigrationService.MIGRATION_TARGET_VERSION
    assert migrated_intent["migration_status"] == "MIGRATED_V2"
    assert migrated_intent["payout_paise"] == 2450000
    assert migrated_intent["environment"] == "SANDBOX"

    # Run 2nd migration pass (Idempotence check)
    stats_pass2 = migration_svc.run_full_migration()
    assert stats_pass2["payments_migrated"] == 0
    assert stats_pass2["payments_already_v2"] == 1
    assert stats_pass2["credits_migrated"] == 0
    assert stats_pass2["credits_already_v2"] == 1
    assert stats_pass2["decisions_migrated"] == 0
    assert stats_pass2["decisions_already_v2"] == 1

    # Record content remains untouched and pristine
    migrated_intent_after = clean_store.get_payment_intent("idemp_mig_01")
    assert migrated_intent_after == migrated_intent


def test_migration_service_restart_safety(clean_store):
    """
    Verifies restart safety: if a migration is interrupted halfway through
    a batch, resuming does not double-migrate or corrupt existing data.
    """
    migration_svc = MigrationService(clean_store)

    # Pre-populate 3 payment intents
    for i in range(1, 4):
        clean_store.save_payment_intent({
            "instruction_id": f"INS-RESTART-{i}",
            "invoice_number": f"INV-RESTART-{i}",
            "vendor_id": "VEND-RESTART",
            "gross_amount": "1000.00",
            "settlement_amount": "1000.00",
            "idempotency_key": f"idemp_restart_{i}",
            "status": "PENDING"
        })

    # Migrate ONLY the first item manually
    first_item = clean_store.get_payment_intent("idemp_restart_1")
    migrated_first, _ = migration_svc.migrate_payment_record(first_item)
    clean_store.save_payment_intent(migrated_first)

    # Resume full migration across all 3
    resume_stats = migration_svc.run_full_migration()
    assert resume_stats["payments_migrated"] == 2
    assert resume_stats["payments_already_v2"] == 1

    # All 3 records are now safely at target version
    for i in range(1, 4):
        doc = clean_store.get_payment_intent(f"idemp_restart_{i}")
        assert doc["schema_version"] == MigrationService.MIGRATION_TARGET_VERSION
        assert doc["payout_paise"] == 100000


# ==============================================================================
# 3. OBSERVABILITY & CREDENTIAL REDACTION (Prompt 11 Rule 6)
# ==============================================================================

def test_observability_credential_and_pii_redaction():
    """
    Verifies that passwords, bearer tokens, private keys, and bank account numbers
    are strictly redacted or masked, while safe correlation keys are preserved.
    """
    raw_payload = {
        "user_id": "usr_9988",
        "api_key": "live_sec_abcdef1234567890",
        "client_secret": "super_secret_client_token",
        "password": "Password123!",
        "auth_header": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.dummy_token",
        "notes": "Paid with Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.dummy_token inside note",
        "account_number": "123456789012",
        "bank_account": "98765432109876",
        "source_account": "5544",
        "idempotency_key": "idemp_safe_key_123",
        "lock_key": "lock_disbursal_001",
        "key_version": "v1.2",
        "private_key": "-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEA0\n-----END RSA PRIVATE KEY-----"
    }

    sanitized = sanitize_sensitive_data(raw_payload)

    # Secrets strictly redacted
    assert sanitized["api_key"] == "[REDACTED]"
    assert sanitized["client_secret"] == "[REDACTED]"
    assert sanitized["password"] == "[REDACTED]"
    assert sanitized["auth_header"] == "[REDACTED]"
    assert sanitized["notes"] == "Paid with Bearer [REDACTED] inside note"
    assert sanitized["private_key"] == "[REDACTED]"

    # Bank account numbers masked to last 4 digits
    assert sanitized["account_number"] == "***9012"
    assert sanitized["bank_account"] == "***9876"
    assert sanitized["source_account"] == "***5544"

    # Safe keys PRESERVED
    assert sanitized["idempotency_key"] == "idemp_safe_key_123"
    assert sanitized["lock_key"] == "lock_disbursal_001"
    assert sanitized["key_version"] == "v1.2"


def test_observability_high_risk_event_logging(clean_security_logger):
    """
    Verifies that all required high-risk operational states are logged
    with safe correlation IDs and structured JSON representation.
    """
    logger = clean_security_logger

    # 1. ambiguous_payment
    logger.log_ambiguous_payment(
        intent_id="INS-AMB-01",
        provider_reference="pout_test_amb",
        details={"gateway_status": "504_GATEWAY_TIMEOUT"}
    )

    # 2. duplicate_submission_suppressed
    logger.log_duplicate_submission_suppressed(
        invoice_id="INV-DUP-01",
        idempotency_key="idemp_dup_01"
    )

    # 3. outbox_retry
    logger.log_outbox_retry(
        event_id="EVT-OUTBOX-99",
        attempt_count=3,
        max_attempts=5
    )

    # 4. simulation_production_gate_rejected
    logger.log_simulation_production_gate_rejected(
        intent_id="INS-GATE-01",
        requested_env="PRODUCTION",
        reason="Missing PRODUCTION_TRUST proof"
    )

    # 5. manual_override
    logger.log_manual_override(
        actor="checker_cfouser",
        action="PAYMENT_TERMS",
        reason="Contract renegotiation"
    )

    audit_trail = logger.get_audit_trail()
    assert len(audit_trail) == 5

    event_types = [e["event_type"] for e in audit_trail]
    assert HighRiskEvent.AMBIGUOUS_PAYMENT.value in event_types
    assert HighRiskEvent.DUPLICATE_SUBMISSION_SUPPRESSED.value in event_types
    assert HighRiskEvent.OUTBOX_RETRY.value in event_types
    assert HighRiskEvent.SIMULATION_PRODUCTION_GATE_REJECTED.value in event_types
    assert HighRiskEvent.MANUAL_OVERRIDE.value in event_types

    # Correlation checks
    amb_event = next(e for e in audit_trail if e["event_type"] == HighRiskEvent.AMBIGUOUS_PAYMENT.value)
    assert amb_event["correlation"]["payment_intent_id"] == "INS-AMB-01"
    assert amb_event["correlation"]["provider_reference"] == "pout_test_amb"

    dup_event = next(e for e in audit_trail if e["event_type"] == HighRiskEvent.DUPLICATE_SUBMISSION_SUPPRESSED.value)
    assert dup_event["correlation"]["invoice_id"] == "INV-DUP-01"
    assert dup_event["correlation"]["correlation_id"] == "idemp_dup_01"


# ==============================================================================
# 4. ENVIRONMENT SAFETY (Prompt 11 Rule 8)
# ==============================================================================

def test_environment_normalization_fails_safe():
    """
    Verifies that missing, None, empty string, or unrecognized environments
    NEVER default to PRODUCTION; they must fail safe to SANDBOX.
    """
    assert normalize_environment(None) == SystemEnvironment.SANDBOX.value
    assert normalize_environment("") == SystemEnvironment.SANDBOX.value
    assert normalize_environment("   ") == SystemEnvironment.SANDBOX.value
    assert normalize_environment("INVALID_ENV") == SystemEnvironment.SANDBOX.value
    assert normalize_environment("PROD") == SystemEnvironment.SANDBOX.value  # Not exact "PRODUCTION"
    assert normalize_environment("production_preview") == SystemEnvironment.SANDBOX.value

    # Legitimate values
    assert normalize_environment("production") == SystemEnvironment.PRODUCTION.value
    assert normalize_environment("PRODUCTION") == SystemEnvironment.PRODUCTION.value
    assert normalize_environment("simulation") == SystemEnvironment.SIMULATION.value
    assert normalize_environment("TEST") == SystemEnvironment.TEST.value
    assert normalize_environment("SANDBOX") == SystemEnvironment.SANDBOX.value


def test_production_payment_gating_blocks_unverified(clean_store, clean_security_logger):
    """
    Verifies that attempting to disburse an intent targeted for PRODUCTION
    without PRODUCTION_TRUST verification evidence or audited override
    is strictly rejected and logged as a high-risk security event.
    """
    from razorpayx_client import RazorpayXBankingClient
    mock_banking = RazorpayXBankingClient("rzp_test_key", "rzp_test_secret", "2323230000000001")
    orchestrator = PaymentOrchestrator(clean_store, banking_client=mock_banking)

    intent = PaymentInstruction(
        instruction_id="INS-PROD-GATED-01",
        invoice_number="INV-PROD-99",
        vendor_id="VEND-UNVERIFIED",
        vendor_pan="AAACB1234K",
        fund_account_id="fa_unverified",
        gross_subtotal=Decimal("10000.00"),
        tax_amount=Decimal("0.00"),
        tds_withheld=Decimal("0.00"),
        tds_section=TDSSection.NONE,
        applied_credits_total=Decimal("0.00"),
        net_payout_amount=Decimal("10000.00"),
        payout_paise=1000000,
        idempotency_key="idemp_prod_gate_01",
        requires_zero_payout_hold=False,
        status=PaymentState.READY_FOR_SUBMISSION,
        environment="PRODUCTION",
        bank_verification_trust="UNVERIFIED"  # Not PRODUCTION_TRUST
    )

    with pytest.raises(PaymentOrchestrationError) as excinfo:
        orchestrator.dispatch_payment_intent(intent)

    assert "Production Payout Gated" in str(excinfo.value)

    # Check security audit log
    audit_trail = clean_security_logger.get_audit_trail()
    rejected_events = [
        e for e in audit_trail
        if e["event_type"] == HighRiskEvent.SIMULATION_PRODUCTION_GATE_REJECTED.value
    ]
    assert len(rejected_events) >= 1
    assert rejected_events[0]["correlation"]["payment_intent_id"] == "INS-PROD-GATED-01"


# ==============================================================================
# 5. CANONICAL UTC TIME SEMANTICS (Prompt 11 Rule 5)
# ==============================================================================

def test_canonical_utc_time_semantics_and_distinction():
    """
    Verifies that financial time fields distinguish occurred_at, received_at,
    submitted_at, and settled_at, and enforce UTC ISO-8601 formatting.
    """
    now_utc = datetime.now(timezone.utc)
    now_iso = now_utc.isoformat()

    intent = PaymentInstruction(
        instruction_id="INS-TIME-01",
        invoice_number="INV-TIME-01",
        vendor_id="VEND-01",
        vendor_pan="AAACB1234K",
        fund_account_id="fa_01",
        gross_subtotal=Decimal("5000.00"),
        tax_amount=Decimal("0.00"),
        tds_withheld=Decimal("0.00"),
        tds_section=TDSSection.NONE,
        applied_credits_total=Decimal("0.00"),
        net_payout_amount=Decimal("5000.00"),
        payout_paise=500000,
        idempotency_key="idemp_time_01",
        requires_zero_payout_hold=False,
        status=PaymentState.SETTLED,
        occurred_at=(now_utc - timedelta(hours=2)).isoformat(),
        received_at=(now_utc - timedelta(hours=1)).isoformat(),
        submitted_at=(now_utc - timedelta(minutes=10)).isoformat(),
        settled_at=now_iso
    )

    # Distinction verified
    assert intent.occurred_at < intent.received_at
    assert intent.received_at < intent.submitted_at
    assert intent.submitted_at < intent.settled_at

    # UTC Semantics verified (ISO-8601 UTC contains +00:00 or Z)
    for ts_field in (intent.occurred_at, intent.received_at, intent.submitted_at, intent.settled_at):
        assert "+00:00" in ts_field or ts_field.endswith("Z")


# ==============================================================================
# 6. NON-OVERRIDABLE INVARIANTS LOGGED ON BREACH (Prompt 11 Rule 6 & 10)
# ==============================================================================

def test_non_overridable_invariants_log_to_security_audit(clean_security_logger):
    """
    Verifies that attempting an illegal manual override (duplicate payment,
    credit overconsumption, unbalanced journal) logs an INVARIANT_REJECTION
    to the security audit logger before throwing an exception.
    """
    now_utc = datetime.now(timezone.utc)
    future_expiry = (now_utc + timedelta(hours=2)).isoformat()

    valid_override = ManualOverrideRecord(
        override_id="OVR-TEST-999",
        maker_id="maker_analyst",
        checker_id="checker_director",
        scope=OverrideScope.GENERAL_POLICY,
        justification="Legitimate test justification",
        created_at=now_utc.isoformat(),
        expiry=future_expiry,
        is_active=True
    )

    # 1. Attempt duplicate payment override
    with pytest.raises(NonOverridableInvariantViolationError):
        OverrideGovernor.assert_can_override_duplicate_payment(valid_override, is_economic_duplicate=True)

    # 2. Attempt credit overconsumption override
    with pytest.raises(NonOverridableInvariantViolationError):
        OverrideGovernor.assert_can_override_credit_limit(
            valid_override,
            consumed_amount=Decimal("12000.00"),
            available_amount=Decimal("10000.00")
        )

    # 3. Attempt unbalanced general ledger journal override
    with pytest.raises(NonOverridableInvariantViolationError):
        OverrideGovernor.assert_can_override_unbalanced_journal(
            valid_override,
            total_debits=Decimal("10000.00"),
            total_credits=Decimal("9000.00")
        )

    audit_trail = clean_security_logger.get_audit_trail()
    invariant_events = [
        e for e in audit_trail
        if e["event_type"] == HighRiskEvent.INVARIANT_REJECTION.value
    ]
    assert len(invariant_events) == 3

    invariants_logged = [e["data"]["invariant"] for e in invariant_events]
    assert "NO_DUPLICATE_ECONOMIC_PAYMENT" in invariants_logged
    assert "CREDIT_CONSERVATION" in invariants_logged
    assert "DOUBLE_ENTRY_BALANCE" in invariants_logged
