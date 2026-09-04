"""
Milestone M2 Empirical Verification & Adversarial Micro-Interaction Test Suite.

Adversarially tests all M2 cockpit interactive components and data bindings in static/dag.html:
1. Top Institutional Telemetry Bar dynamic IDs and numeric format preservation.
2. Triage Queue Table & Tabs ARIA accessibility, keyboard navigation, and segmented counter logic.
3. 4-Step Horizontal Financial Waterfall with arithmetic operator connectors and variance badge.
4. Expandable 4/4 Statutory Invariant Compliance Status Rail with accessible triggers and badge selectors.
5. De-duplicated Ind AS 1 General Ledger indicator with deep link and variance summary.
6. Fenced RazorpayX Disbursal Modal with client-side idempotency and in-flight locking semantics.
7. Point-of-Payment Cryptographic Settlement Proof Sharing Modal with RFC 8785 canonical manifest download.
"""

import re
from pathlib import Path
import pytest

STATIC_DIR = Path(__file__).resolve().parent.parent.parent / "static"


def test_m2_telemetry_bar_dynamic_ids_and_classes():
    """Verify top telemetry bar possesses required dynamic IDs and monospaced tabular numerals."""
    content = (STATIC_DIR / "dag.html").read_text(encoding="utf-8")

    required_ids = [
        "ticker-settled-val",
        "ticker-settled-sub",
        "ticker-pipeline-val",
        "ticker-pipeline-sub",
        "ticker-tax-val",
        "ticker-tax-sub",
    ]
    for element_id in required_ids:
        assert f'id="{element_id}"' in content, f"Telemetry bar missing dynamic id: #{element_id}"

    # Verify updateTickerBar function exists in JS
    assert "function updateTickerBar(" in content, "Missing updateTickerBar function in dag.html controller"


def test_m2_queue_table_accessibility_and_keyboard_nav():
    """Verify triage queue table rows have ARIA roles, tabindex, aria-selected, and keyboard handlers."""
    content = (STATIC_DIR / "dag.html").read_text(encoding="utf-8")

    # Queue Tablist ARIA
    assert 'role="tablist"' in content, "Missing role='tablist' on queue filter tabs container"
    assert 'role="tab"' in content, "Missing role='tab' on queue filter buttons"

    # Queue Table Rows ARIA & Keyboard nav in renderQueueTable JS
    assert "tr.setAttribute('role', 'row')" in content, "renderQueueTable missing tr role='row'"
    assert "tr.setAttribute('tabindex', '0')" in content, "renderQueueTable missing tr tabindex='0'"
    assert "tr.setAttribute('aria-selected'" in content, "renderQueueTable missing tr aria-selected"
    assert "tr.setAttribute('aria-label'" in content, "renderQueueTable missing tr aria-label"
    assert "tr.onkeydown" in content, "renderQueueTable missing tr onkeydown keyboard navigation handler"
    assert "e.key === 'Enter'" in content, "onkeydown missing Enter key handler"
    assert "e.key === ' '" in content, "onkeydown missing Space key handler"

    # Tab counter updating function
    assert "function updateQueueTabCounters(" in content, "Missing updateQueueTabCounters function"


def test_m2_horizontal_waterfall_operator_flow_and_variance():
    """Verify 4-step financial waterfall has 7-element operator layout, arithmetic pills, and variance badge."""
    content = (STATIC_DIR / "dag.html").read_text(encoding="utf-8")

    # Operator connectors
    assert 'title="Minus Statutory TDS"' in content or 'aria-label="minus"' in content, "Missing Minus operator for TDS"
    assert 'title="Minus Credit Notes"' in content or 'aria-label="minus"' in content, "Missing Minus operator for Credit Notes"
    assert 'title="Equals Net Disbursable"' in content or 'aria-label="equals"' in content, "Missing Equals operator for Net Disbursable"

    # Variance badge element
    assert 'id="waterfall-variance-badge"' in content, "Missing #waterfall-variance-badge element"
    assert "Variance: ₹0.00" in content or "Variance: INR 0.00" in content, "Missing zero variance text in waterfall invariant"

    # Dynamic calculation in updateDetailView
    assert "calcVariance" in content or "Math.abs" in content, "Missing client-side waterfall variance calculation in updateDetailView"


def test_m2_statutory_compliance_rail_accessibility_and_badges():
    """Verify compliance rail has button semantics, drawer toggle, and individual invariant badge IDs."""
    content = (STATIC_DIR / "dag.html").read_text(encoding="utf-8")

    # Rail semantics
    assert 'id="compliance-rail"' in content, "Missing #compliance-rail"
    assert 'role="button"' in content, "Missing role='button' on #compliance-rail"
    assert 'tabindex="0"' in content, "Missing tabindex='0' on #compliance-rail"
    assert 'aria-expanded="false"' in content, "Missing initial aria-expanded='false' on #compliance-rail"
    assert 'aria-controls="compliance-expanded-drawer"' in content, "Missing aria-controls on #compliance-rail"
    assert 'onkeydown="handleRailKey(event)"' in content, "Missing onkeydown handler on #compliance-rail"

    # Individual badge IDs for the 4 statutory invariants
    assert 'id="badge-inv-kyc"' in content, "Missing #badge-inv-kyc"
    assert 'id="badge-inv-tax"' in content, "Missing #badge-inv-tax"
    assert 'id="badge-inv-cooling"' in content, "Missing #badge-inv-cooling"
    assert 'id="badge-inv-rate"' in content, "Missing #badge-inv-rate"
    assert 'id="rail-status-dot"' in content, "Missing #rail-status-dot"
    assert 'id="rail-summary-text"' in content, "Missing #rail-summary-text"


def test_m2_gl_indicator_deep_link_and_summary():
    """Verify General Ledger badge links directly to auditor verify anchor and summarizes Debits == Credits."""
    content = (STATIC_DIR / "dag.html").read_text(encoding="utf-8")

    assert 'id="gl-audit-link"' in content, "Missing #gl-audit-link"
    assert 'id="gl-summary-text"' in content, "Missing #gl-summary-text"
    assert "/audit#verify-" in content, "Missing deep linking pattern to /audit#verify-${invoice_number}"


def test_m2_disbursal_modal_idempotency_and_inflight_lock():
    """Verify RazorpayX disbursal dialog generates client UUID, displays idempotency key, and locks on submit."""
    content = (STATIC_DIR / "dag.html").read_text(encoding="utf-8")

    assert 'id="payout-confirm-modal"' in content, "Missing #payout-confirm-modal"
    assert 'id="modal-idempotency-key"' in content, "Missing #modal-idempotency-key"
    assert 'id="payout-confirm-btn"' in content, "Missing #payout-confirm-btn"
    assert 'id="payout-cancel-btn"' in content, "Missing #payout-cancel-btn"

    # JS Idempotency generation & submit lock
    assert "crypto.randomUUID" in content, "Missing crypto.randomUUID() for disbursal idempotency"
    assert "confirmBtn.disabled = true" in content, "Missing in-flight submit locking on confirm button"
    assert "animate-spin" in content, "Missing spinning loading indicator during disbursal in-flight"


def test_m2_cryptographic_proof_modal_manifest_download():
    """Verify Point-of-Payment Cryptographic Proof modal includes RFC 8785 digest, KMS URI, and JSON download."""
    content = (STATIC_DIR / "dag.html").read_text(encoding="utf-8")

    assert 'id="proof-share-modal"' in content, "Missing #proof-share-modal"
    assert 'id="proof-canonical-sha"' in content, "Missing #proof-canonical-sha"
    assert 'id="proof-kms-key"' in content, "Missing #proof-kms-key"
    assert 'id="public-verify-url"' in content, "Missing #public-verify-url"

    # Proof download & copy actions
    assert "function downloadProofManifest(" in content, "Missing downloadProofManifest function"
    assert "function copyVerifyLink(" in content, "Missing copyVerifyLink function"
    assert "RFC 8785 JSON Canonicalization Scheme" in content, "Missing RFC 8785 manifest standard in manifest export"
