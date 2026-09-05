# Complete Diff Inventory: Prompts 4–10 Hardening Audit

This document provides a comprehensive inventory of all changes made across the hardening engagement from Prompt 4 through Prompt 10. It establishes backward-compatibility mappings, schema evolutions, and migration requirements to ensure zero breaking changes across all consumers.

---

## Inventory of Changed Modules

### 1. `schemas.py`
- **Purpose**: Core financial data models, strict Pydantic v2 validation, decimal-safe representations, and domain separation.
- **Affected Domain**: Shared Financial Core, Payments, Tax, Procurement, Accounting, Audit, Governance.
- **Public Interfaces Changed**:
  - Added strict decimal ingress validators (`reject_binary_float_ingress`) preventing IEEE-754 float drift.
  - Added `DuplicateDisposition` enum and `DuplicateCheckResult` model.
  - Added `StateTransitionRecord` and `WebhookEventRecord` models.
  - Added `OverrideScope` enum and `ManualOverrideRecord` model (with `validate_maker_checker` and `is_expired`).
  - Added `FieldProvenanceRecord`, `InvoiceDocumentLineage`, and `ReplayExecutionResult`.
  - Added `FinancialPosition` enforcing mathematical conservation across Commercial, Tax, Credit, Retention, and Settlement.
  - Enriched `DecisionRecord` with attestation context: snapshot hashes, policy versions, evidence digests.
- **Persisted Schema Changed**:
  - `PaymentInstruction`: added `financial_snapshot_hash`, `version`, `attempt_count`, `environment`, `trust`.
  - `OpenCreditRecord`: added `original_amount`, `available_amount`, `reserved_amount`, `consumed_amount`.
  - `ProcurementAllocationRecord`: added `allocated_quantity`, `state`, `version`.
- **Worker/Event Payload Changed**: Added structured fields; all new fields have safe optional defaults.
- **Frontend Contract Changed**: Preserved backwards compatibility. Legacy aliases (`gross_amount`, `available_balance`, `settlement_amount`) remain supported.
- **Migration Required**: Backfill missing fields for historical records.
- **Fallback / Default Behavior**: Missing fields default to safe unversioned or legacy fallbacks (`available_balance` used if `available_amount` is absent; missing policy version defaults to `"LEGACY_UNVERSIONED"`).

---

### 2. `firestore_store.py`
- **Purpose**: Append-only transactional persistence, distributed leasing, outbox items, and immutability fences.
- **Affected Domain**: State Store, Payments, General Ledger, Audit, Concurrency.
- **Public Interfaces Changed**:
  - Added `PostedDecisionMutationError` and `PostedJournalMutationError`.
  - Added `atomic_register_invoice_business_key(business_key, content_hash, metadata)`.
  - Added `save_webhook_event(event_dict)` and `get_webhook_event(event_id)`.
  - Added `record_state_transition(transition_dict)` and `get_state_transitions(idempotency_key)`.
  - Added `save_retention_record`, `get_retention_record`, `update_retention_record`.
  - Added `save_outbox_item`, `get_outbox_item`, `get_pending_outbox_items`, `update_outbox_item`.
- **Persisted Schema Changed**: New collections: `webhook_events`, `state_transitions`, `registered_business_keys`, `gst_retentions`, `payment_outbox`.
- **Worker/Event Payload Changed**: Outbox work items stored with explicit state (`PENDING`, `PROCESSING`, `COMPLETED`, `AMBIGUOUS`).
- **Frontend Contract Changed**: None.
- **Migration Required**: None for existing collections; new collections created on first write.
- **Fallback / Default Behavior**: If Firestore is unreachable, falls back to thread-safe in-memory mock dictionary.

---

### 3. `services/payment_orchestrator.py`
- **Purpose**: Durable payment intent orchestration, transactional outbox pattern, state machine transitions, and ambiguous outcome fencing.
- **Affected Domain**: Payment Execution, Treasury, Banking Rails.
- **Public Interfaces Changed**:
  - Added `PaymentStateMachine` with `validate_transition` and optimistic lock verification.
  - Added `PaymentOrchestrator` methods: `get_or_create_payment_intent`, `create_outbox_work_item`, `dispatch_payment_intent`, `reconcile_ambiguous_intent`, and `execute_high_risk_reconciliation_action`.
  - Added exceptions: `PaymentMaterialConflictError`, `PaymentStaleVersionError`, `PaymentAmbiguousOutcomeError`.
- **Persisted Schema Changed**: `PaymentInstruction` and `OutboxWorkItem`.
- **Worker/Event Payload Changed**: Outbox worker polls `payment_outbox` for `PENDING`/`AMBIGUOUS` items.
- **Frontend Contract Changed**: None. Endpoints return normalized status.
- **Migration Required**: Dual-read compatibility ensures legacy payment records parse cleanly.
- **Fallback / Default Behavior**: In-flight timeouts transition to `UNKNOWN`/`AMBIGUOUS` without blind duplicate dispatch.

---

### 4. `services/webhook_service.py`
- **Purpose**: Webhook authentication, replay protection, event deduplication, and out-of-order callback convergence.
- **Affected Domain**: Banking Callbacks, Webhook Security.
- **Public Interfaces Changed**:
  - `ProviderWebhookService.verify_signature(raw_body, signature, secret)`.
  - `ProviderWebhookService.process_razorpayx_webhook(raw_body, signature, secret, current_time_epoch)`.
  - Exceptions: `WebhookAuthenticationError`, `WebhookReplayError`.
- **Persisted Schema Changed**: `webhook_events` collection.
- **Worker/Event Payload Changed**: RazorpayX webhook payloads parsed, verified, and mapped to payment intents.
- **Frontend Contract Changed**: None. Webhook endpoint returns HTTP 200 with structured status.
- **Migration Required**: None.
- **Fallback / Default Behavior**: Out-of-order callbacks arriving after `SETTLED` preserve terminal state. Reversals are fenced in `REVERSAL_PENDING_APPROVAL`.

---

### 5. `services/override_governor.py`
- **Purpose**: Authoritative manual override governance, maker-checker segregation of duties, and non-overridable invariant fencing.
- **Affected Domain**: Governance, Compliance, Internal Controls.
- **Public Interfaces Changed**:
  - `OverrideGovernor.validate_override(override, required_scope, current_time)`.
  - Assertions: `assert_can_override_duplicate_payment`, `assert_can_override_credit_limit`, `assert_can_override_unbalanced_journal`, `assert_can_override_historical_mutation`, `assert_can_override_simulation_mode`, `assert_can_override_po_quantity`.
  - Exceptions: `MakerCheckerViolationError`, `OverrideExpiredError`, `InsufficientOverrideScopeError`, `NonOverridableInvariantViolationError`.
- **Persisted Schema Changed**: `ManualOverrideRecord`.
- **Worker/Event Payload Changed**: None.
- **Frontend Contract Changed**: None.
- **Migration Required**: None.
- **Fallback / Default Behavior**: Unapproved or invalid overrides block processing.

---

### 6. `services/duplicate_detector.py`
- **Purpose**: 5-layer duplicate invoice prevention engine (`BLOCK` vs `REVIEW` vs `ALLOW`).
- **Affected Domain**: Invoice Ingestion, Fraud Prevention.
- **Public Interfaces Changed**:
  - `MultiSignalDuplicateDetector.normalize_invoice_number(raw)`.
  - `MultiSignalDuplicateDetector.evaluate_invoice(...) -> DuplicateCheckResult`.
  - Backward-compatible `check_for_duplicates(...) -> Tuple[bool, Optional[str]]`.
- **Persisted Schema Changed**: `DuplicateCheckResult`.
- **Worker/Event Payload Changed**: Returns `DuplicateCheckResult` with disposition (`BLOCK`, `REVIEW`, `ALLOW`).
- **Frontend Contract Changed**: Compatible with existing exception display.
- **Migration Required**: None.
- **Fallback / Default Behavior**: Clean invoices default to `ALLOW`. Recurring similar invoices route to `REVIEW` instead of false permanent rejection.

---

### 7. `services/po_registry.py` & `services/po_matching.py`
- **Purpose**: Cumulative line-item quantity tracking across POs and GRNs, versioned PO snapshots, and price/quantity tolerance enforcement.
- **Affected Domain**: Procurement 3-Way Match.
- **Public Interfaces Changed**:
  - `EnterprisePORegistry.reserve_allocation` and `commit_allocation`.
  - `CumulativeMatchingEngine.evaluate_invoice_cumulative_match`.
- **Persisted Schema Changed**: `procurement_allocations` collection.
- **Worker/Event Payload Changed**: Line items bind to `po_line_id` and cumulative allocated quantities.
- **Frontend Contract Changed**: Backward compatible.
- **Migration Required**: None.
- **Fallback / Default Behavior**: If no prior allocation exists, starts cumulative total at 0.00.

---

### 8. `services/tax_gstr2b.py` & `tax_engine.py`
- **Purpose**: Statutory GST/TDS calculation, dual-Act boundary transition (1961 vs 2025), and GSTR-2B split settlement with retention escrow.
- **Affected Domain**: Statutory Tax, Treasury Retention.
- **Public Interfaces Changed**:
  - `GSTR2BSplitSettlementEngine.calculate_split_settlement`.
  - `StatutoryComplianceTaxEngine` keyword argument resilience.
- **Persisted Schema Changed**: `gst_retentions` collection.
- **Worker/Event Payload Changed**: Split settlement returns `immediate_base_disbursal` and `gst_retention_escrow`.
- **Frontend Contract Changed**: None.
- **Migration Required**: None.
- **Fallback / Default Behavior**: Unmatched GSTR-2B holds GST in retention escrow while immediately disbursing base amount.

---

### 9. `services/ledger.py` & `services/erp_exporter.py`
- **Purpose**: Decimal numeric safety, credit conservation invariants, atomic netting, and double-entry Ind AS 1 / IFRS journal formatting.
- **Affected Domain**: General Ledger, ERP Export, Accounting.
- **Public Interfaces Changed**:
  - `LedgerNettingEngine.apply_credits_and_advances` (atomic reservation).
  - `ERPJournalExporter.generate_reversal_voucher` and `generate_replacement_voucher`.
- **Persisted Schema Changed**: `general_ledger_journals` collection.
- **Worker/Event Payload Changed**: Reversal and replacement vouchers preserve explicit lineage references (`original_entry_id`, `reversal_entry_id`, `replacement_entry_id`).
- **Frontend Contract Changed**: None.
- **Migration Required**: None.
- **Fallback / Default Behavior**: Mathematical assertion strictly verifies Debits == Credits before persistence.

---

### 10. `services/policy_registry.py` & `services/lineage.py`
- **Purpose**: Enterprise policy versioning, immutable policy registry, point-in-time policy resolution, and deterministic historical replay.
- **Affected Domain**: Policy Governance, Audit, Decision Replay.
- **Public Interfaces Changed**:
  - `EnterprisePolicyRegistry` with `register_policy`, `resolve_policy_at`.
  - `DecisionReplayEngine.execute_replay` supporting `HISTORICAL_REPLAY` and `WHAT_IF_REPLAY`.
- **Persisted Schema Changed**: `enterprise_policies` collection.
- **Worker/Event Payload Changed**: Signed decisions attest to all 8 policy versions.
- **Frontend Contract Changed**: None.
- **Migration Required**: None.
- **Fallback / Default Behavior**: Unversioned decisions default to `"LEGACY_UNVERSIONED"` rather than falsely claiming 2026 attestation.

---

### 11. `services/penny_drop.py`
- **Purpose**: Bank account verification, NPCI penny drop name matching, velocity tracking, and cooling-off periods.
- **Affected Domain**: Bank Security, Fraud Prevention.
- **Public Interfaces Changed**:
  - `PennyDropValidationEngine.verify_beneficiary_account` with multi-signal score and cooling periods.
- **Persisted Schema Changed**: `VendorBankSecurityStatus`.
- **Worker/Event Payload Changed**: None.
- **Frontend Contract Changed**: None.
- **Migration Required**: None.
- **Fallback / Default Behavior**: New bank accounts enforce 48-hour cooling period unless overridden by dual-control approval.
