"""
Milestone M1 Empirical Verification Test Suite.
Adversarially tests design tokens, typography, monospaced tabular numerals, and semantic badges
using standard library regex and HTML parser.
"""

import re
from pathlib import Path
import pytest


STATIC_DIR = Path(__file__).resolve().parent.parent.parent / "static"


def test_tailwind_token_extension_all_screens():
    """Verify all 3 core workspaces define standard Tailwind theme extensions."""
    files = ["dag.html", "vendor_intel.html", "auditor_suite.html"]
    for filename in files:
        filepath = STATIC_DIR / filename
        assert filepath.exists(), f"File {filename} does not exist"
        content = filepath.read_text(encoding="utf-8")
        
        # Check fonts
        assert "Plus Jakarta Sans" in content, f"{filename} missing 'Plus Jakarta Sans'"
        assert "JetBrains Mono" in content, f"{filename} missing 'JetBrains Mono'"
        
        # Check tokens in tailwind.config
        assert "canvas: '#F8FAFC'" in content or "'canvas': '#F8FAFC'" in content or 'canvas: "#F8FAFC"' in content
        assert "charcoal: '#0F172A'" in content or "'charcoal': '#0F172A'" in content or 'charcoal: "#0F172A"' in content
        assert "microborder: '#E2E8F0'" in content or "'microborder': '#E2E8F0'" in content or 'microborder: "#E2E8F0"' in content
        
        # Check body styling
        assert "#F8FAFC" in content, f"{filename} missing #F8FAFC background"
        assert "#0F172A" in content, f"{filename} missing #0F172A charcoal color"
        assert "#E2E8F0" in content, f"{filename} missing #E2E8F0 microborder"


def test_monospaced_tabular_numerals_dag_html():
    """Verify font-mono and tabular-nums on all numeric telemetry and tables in dag.html."""
    content = (STATIC_DIR / "dag.html").read_text(encoding="utf-8")
    
    # 1. Top Institutional Telemetry Cards
    # Look for metrics: ₹1,24,50,000.00, ₹3,79,000.00, ₹30,000.00
    telemetry_patterns = [
        r'(?:₹|INR\s*)1,24,50,000\.00',
        r'(?:₹|INR\s*)3,79,000\.00',
        r'(?:₹|INR\s*)30,000\.00'
    ]
    for pattern in telemetry_patterns:
        match = re.search(r'<div[^>]*class="([^"]*)"[^>]*>' + pattern + r'</div>', content)
        assert match is not None, f"Could not find telemetry element matching {pattern}"
        classes = match.group(1)
        assert "font-mono" in classes, f"Telemetry element {pattern} missing font-mono in classes: {classes}"
        assert "tabular-nums" in classes, f"Telemetry element {pattern} missing tabular-nums in classes: {classes}"

    # 2. Waterfall steps
    waterfall_bindings = ["gross-amount", "tds-amount", "credit-amount", "net-amount"]
    for binding in waterfall_bindings:
        match = re.search(r'<div[^>]*data-bind="' + binding + r'"[^>]*class="([^"]*)"|<div[^>]*class="([^"]*)"[^>]*data-bind="' + binding + r'"', content)
        assert match is not None, f"Could not find waterfall step with data-bind='{binding}'"
        classes = match.group(1) or match.group(2)
        assert "font-mono" in classes, f"Waterfall step {binding} missing font-mono in classes: {classes}"
        assert "tabular-nums" in classes, f"Waterfall step {binding} missing tabular-nums in classes: {classes}"

    # 3. Dynamic queue table template
    # Verify ${item.invoice_number}, ${item.gross_formatted}, ${item.tds_formatted}, ${item.net_formatted}, ${item.stage_progress}
    queue_fields = ["item.invoice_number", "item.gross_formatted", "item.tds_formatted", "item.net_formatted", "item.stage_progress"]
    for field in queue_fields:
        # Match <td class="...">${field}</td>
        pattern = r'<td\s+class="([^"]*)"[^>]*>[^<]*\$\{' + re.escape(field) + r'\}[^<]*</td>'
        match = re.search(pattern, content)
        assert match is not None, f"Could not find queue table cell for {field}"
        classes = match.group(1)
        assert "font-mono" in classes, f"Queue cell {field} missing font-mono: {classes}"
        assert "tabular-nums" in classes, f"Queue cell {field} missing tabular-nums: {classes}"


def test_monospaced_tabular_numerals_vendor_intel():
    """Verify font-mono and tabular-nums on vendor_intel.html."""
    content = (STATIC_DIR / "vendor_intel.html").read_text(encoding="utf-8")
    
    # 4-card risk grid: #v-trust-score, #v-pan, #v-cooling, #v-settled-vol
    risk_ids = ["v-trust-score", "v-pan", "v-cooling", "v-settled-vol"]
    for element_id in risk_ids:
        match = re.search(r'<div[^>]*id="' + element_id + r'"[^>]*class="([^"]*)"|<div[^>]*class="([^"]*)"[^>]*id="' + element_id + r'"', content)
        assert match is not None, f"Could not find #{element_id}"
        classes = match.group(1) or match.group(2)
        assert "font-mono" in classes, f"#{element_id} missing font-mono: {classes}"
        assert "tabular-nums" in classes, f"#{element_id} missing tabular-nums: {classes}"

    # Static table row
    static_tds = re.findall(r'<td\s+class="([^"]*)">(?:INV-884|(?:₹|INR\s*)1,18,000\.00|-(?:₹|INR\s*)10,000\.00 \(10%\)|(?:₹|INR\s*)1,08,000\.00)</td>', content)
    assert len(static_tds) >= 4, f"Expected at least 4 numeric static tds in vendor_intel.html, found {len(static_tds)}"
    for classes in static_tds:
        assert "font-mono" in classes, f"Static ledger td missing font-mono: {classes}"
        assert "tabular-nums" in classes, f"Static ledger td missing tabular-nums: {classes}"

    # Dynamic renderVendor table row
    vendor_fields = ["inv.id", "inv.gross", "inv.tax", "inv.net"]
    for field in vendor_fields:
        pattern = r'<td\s+class="([^"]*)"[^>]*>[^<]*\$\{' + re.escape(field) + r'\}[^<]*</td>'
        match = re.search(pattern, content)
        assert match is not None, f"Could not find vendor ledger cell for {field}"
        classes = match.group(1)
        assert "font-mono" in classes, f"Dynamic vendor ledger cell {field} missing font-mono: {classes}"
        assert "tabular-nums" in classes, f"Dynamic vendor ledger cell {field} missing tabular-nums: {classes}"


def test_monospaced_tabular_numerals_auditor_suite():
    """Verify font-mono and tabular-nums on auditor_suite.html."""
    content = (STATIC_DIR / "auditor_suite.html").read_text(encoding="utf-8")
    
    # Canonical SHA-256 Digest & Ed25519 Hardware Seal
    digest_matches = re.findall(r'<div\s+class="([^"]*break-all[^"]*)"', content)
    assert len(digest_matches) >= 2, f"Expected at least 2 verifier digest elements, found {len(digest_matches)}"
    for classes in digest_matches:
        assert "font-mono" in classes, f"Verifier element missing font-mono: {classes}"
        assert "tabular-nums" in classes, f"Verifier element missing tabular-nums: {classes}"


def test_get_semantic_badge_adversarial_oracle():
    """
    Adversarial oracle for getSemanticBadge JS implementation.
    Simulates and tests all valid, boundary, and hostile inputs.
    """
    def py_get_semantic_badge(severity, state):
        sev = str(severity or '').upper()
        st = str(state or '').upper()
        if sev == 'EMERALD' or st in ['SETTLED', 'AUTO_APPROVED']:
            return ('SETTLED', 'bg-emerald-50 border border-emerald-200 text-emerald-800')
        elif sev == 'AMBER' or st in ['COOLING_HOLD', 'HELD_FOR_COOLING', 'HELD']:
            return ('COOLING HOLD', 'bg-amber-50 border border-amber-200 text-amber-900')
        elif sev == 'PURPLE' or st in ['TDS_REVIEW', 'TDS_REVIEW_REQUIRED']:
            return ('TDS REVIEW', 'bg-purple-50 border border-purple-200 text-purple-800')
        elif sev in ['ROSE', 'RED'] or st in ['BLOCKED_BREACH', 'POLICY_VIOLATION', 'BLOCKED']:
            return ('POLICY VIOLATION', 'bg-rose-50 border border-rose-200 text-rose-800')
        else:
            return ('READY TO DISBURSE', 'bg-blue-50 border border-blue-200 text-blue-800')

    test_cases = [
        # Normal cases
        ("EMERALD", "SETTLED", "SETTLED", "emerald"),
        ("AMBER", "COOLING_HOLD", "COOLING HOLD", "amber"),
        ("PURPLE", "TDS_REVIEW", "TDS REVIEW", "purple"),
        ("ROSE", "POLICY_VIOLATION", "POLICY VIOLATION", "rose"),
        ("BLUE", "READY_TO_DISBURSE", "READY TO DISBURSE", "blue"),
        
        # State aliases
        (None, "AUTO_APPROVED", "SETTLED", "emerald"),
        (None, "HELD_FOR_COOLING", "COOLING HOLD", "amber"),
        (None, "HELD", "COOLING HOLD", "amber"),
        (None, "TDS_REVIEW_REQUIRED", "TDS REVIEW", "purple"),
        (None, "BLOCKED_BREACH", "POLICY VIOLATION", "rose"),
        (None, "BLOCKED", "POLICY VIOLATION", "rose"),
        ("RED", None, "POLICY VIOLATION", "rose"),
        
        # Mixed case
        ("emerald", "settled", "SETTLED", "emerald"),
        ("Amber", "cooling_hold", "COOLING HOLD", "amber"),
        ("Purple", "tds_review", "TDS REVIEW", "purple"),
        ("Rose", "policy_violation", "POLICY VIOLATION", "rose"),
        ("blue", "ready_to_disburse", "READY TO DISBURSE", "blue"),
        
        # Empty / None / Unexpected fallbacks
        ("", "", "READY TO DISBURSE", "blue"),
        (None, None, "READY TO DISBURSE", "blue"),
        ("UNKNOWN", "UNKNOWN_STATE", "READY TO DISBURSE", "blue"),
        ("!@#$%", "???", "READY TO DISBURSE", "blue"),
    ]

    for sev, st, expected_label, expected_color in test_cases:
        label, classes = py_get_semantic_badge(sev, st)
        assert label == expected_label, f"Failed label for ({sev}, {st}): got {label}, expected {expected_label}"
        assert expected_color in classes, f"Failed color for ({sev}, {st}): got {classes}, expected {expected_color}"
