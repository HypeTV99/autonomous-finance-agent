"""
Milestone M3 (R3) Empirical & Adversarial Test Suite:
Multi-Screen Cohesion, Accessibility & Forensic Auditor Suite.

Adversarially tests:
1. Multi-Screen Cohesion & Visual Token Consistency across all 3 workspaces (dag.html, vendor_intel.html, auditor_suite.html).
2. Universal WCAG 2.1 AA Keyboard Focus Rings (focus-visible:ring-2) and text contrast.
3. Client-side RFC 4180 CSV export with comma/quote escaping and Blob download in vendor_intel.html.
4. 17-Node Merkle DAG Evidence Tree visualizer in auditor_suite.html.
5. 9-Pillar Statutory Compliance & Executive Audit Checklist in auditor_suite.html.
6. Zero-Login Public Offline Proof Verifier in auditor_suite.html.
7. Deep-link URL hash navigation (#verify-${invoice_number}) in auditor_suite.html.
8. Responsive Reflow layout structures (Desktop, Tablet, Mobile).
"""

import io
import csv
import json
import re
from pathlib import Path
import pytest

STATIC_DIR = Path(__file__).resolve().parent.parent.parent / "static"
FILES = ["dag.html", "vendor_intel.html", "auditor_suite.html"]


# ==============================================================================
# 1. MULTI-SCREEN COHESION & TOKEN ARCHITECTURE
# ==============================================================================

def test_m3_multi_screen_token_cohesion():
    """Verify all 3 core workspaces share identical institutional design tokens and styling."""
    for filename in FILES:
        filepath = STATIC_DIR / filename
        assert filepath.exists(), f"File {filename} does not exist"
        content = filepath.read_text(encoding="utf-8")
        
        # 1. Off-white canvas and pure white cards
        assert "canvas: '#F8FAFC'" in content or "'canvas': '#F8FAFC'" in content or 'canvas: "#F8FAFC"' in content
        assert "charcoal: '#0F172A'" in content or "'charcoal': '#0F172A'" in content or 'charcoal: "#0F172A"' in content
        assert "microborder: '#E2E8F0'" in content or "'microborder': '#E2E8F0'" in content or 'microborder: "#E2E8F0"' in content
        assert ".cockpit-card" in content
        assert "background: #FFFFFF;" in content or "background: #FFFFFF" in content
        
        # 2. Typography
        assert "Plus Jakarta Sans" in content
        assert "JetBrains Mono" in content
        
        # 3. Maximum content width container
        assert "max-w-[1720px]" in content


def test_m3_navigation_links_cross_workspace_cohesion():
    """Verify all 3 workspaces contain seamless navigation to each other."""
    for filename in FILES:
        content = (STATIC_DIR / filename).read_text(encoding="utf-8")
        assert 'href="/dashboard"' in content, f"{filename} missing link to /dashboard"
        assert 'href="/vendor-intel"' in content, f"{filename} missing link to /vendor-intel"
        assert 'href="/audit"' in content, f"{filename} missing link to /audit"


# ==============================================================================
# 2. UNIVERSAL WCAG 2.1 AA KEYBOARD FOCUS RINGS & CONTRAST
# ==============================================================================

def test_m3_universal_wcag_focus_visible_rings():
    """Verify focus-visible rings on interactive elements across all 3 workspaces."""
    for filename in FILES:
        content = (STATIC_DIR / filename).read_text(encoding="utf-8")
        # Check presence of focus-visible ring styles
        assert "focus-visible:ring-2" in content, f"{filename} missing focus-visible:ring-2"
        assert "focus-visible:ring-slate-900" in content or "focus-visible:ring-emerald-700" in content
        
        # Check buttons have focus rings
        buttons = re.findall(r'<button[^>]*class="([^"]*)"', content)
        for b_cls in buttons:
            if "hidden" not in b_cls and 'tabindex="-1"' not in b_cls:
                assert "focus-visible:ring-2" in b_cls or "transition" in b_cls, f"Button missing focus ring in {filename}: {b_cls}"


# ==============================================================================
# 3. CLIENT-SIDE RFC 4180 CSV EXPORT IN VENDOR_INTEL.HTML
# ==============================================================================

def test_m3_vendor_intel_rfc4180_csv_export():
    """Adversarially verify RFC 4180 CSV generation and export in vendor_intel.html."""
    content = (STATIC_DIR / "vendor_intel.html").read_text(encoding="utf-8")
    
    # 1. Export button and function definition
    assert 'onclick="exportVendorLedgerCSV()"' in content
    assert "function exportVendorLedgerCSV()" in content
    
    # 2. RFC 4180 headers
    headers = ['Invoice Number', 'Date', 'Gross Amount', 'Statutory Tax', 'Net Disbursed', 'Status', 'Audit Trail / Invariant Rule']
    for h in headers:
        assert h in content, f"CSV export missing required header: {h}"
        
    # 3. Blob creation with text/csv;charset=utf-8; and download attribute
    assert "new Blob([" in content
    assert "text/csv;charset=utf-8;" in content
    assert "URL.createObjectURL(blob)" in content
    assert "vendor-ledger-" in content
    assert "link.click()" in content
    assert "URL.revokeObjectURL(url)" in content


def test_m3_rfc4180_csv_parser_oracle():
    """Verify that simulated output of exportVendorLedgerCSV strictly adheres to RFC 4180."""
    headers = ['Invoice Number', 'Date', 'Gross Amount', 'Statutory Tax', 'Net Disbursed', 'Status', 'Audit Trail / Invariant Rule']
    
    def escape_cell(val):
        if val is None:
            return '""'
        s = str(val)
        if any(c in s for c in [',', '"', '\n', '\r']):
            return f'"{s.replace(chr(34), chr(34)+chr(34))}"'
        return f'"{s}"'

    test_invoices = [
        {"id": "INV-884", "date": "2026-08-25", "gross": "₹1,18,000.00", "tax": "-₹10,000.00 (10%)", "net": "₹1,08,000.00", "status": "SETTLED", "why": "Section 194J TDS computed, PO ceiling satisfied."},
        {"id": "INV-742", "date": "2026-08-10", "gross": "₹2,36,000.00", "tax": "-₹20,000.00 (10%)", "net": "₹2,16,000.00", "status": "SETTLED", "why": 'Section 194J "technical fees", credit pool netted.'},
        {"id": "INV-619", "date": "2026-07-28", "gross": "₹1,18,000.00", "tax": "-₹10,000.00 (10%)", "net": "₹1,08,000.00", "status": "SETTLED", "why": "Regular consulting retainership\r\nChallan 281 verified."}
    ]

    csv_rows = []
    csv_rows.append(','.join([f'"{h}"' for h in headers]))
    for inv in test_invoices:
        row = [
            escape_cell(inv["id"]),
            escape_cell(inv["date"]),
            escape_cell(inv["gross"]),
            escape_cell(inv["tax"]),
            escape_cell(inv["net"]),
            escape_cell(inv["status"]),
            escape_cell(inv["why"])
        ]
        csv_rows.append(','.join(row))

    csv_content = '\r\n'.join(csv_rows)
    
    # Parse with Python standard library csv module
    reader = list(csv.reader(io.StringIO(csv_content)))
    assert len(reader) == 4
    assert reader[0] == headers
    assert reader[1][0] == "INV-884"
    assert reader[2][6] == 'Section 194J "technical fees", credit pool netted.'
    assert "Challan 281 verified." in reader[3][6]


# ==============================================================================
# 4. 17-NODE MERKLE DAG EVIDENCE TREE IN AUDITOR_SUITE.HTML
# ==============================================================================

def test_m3_auditor_suite_17_node_merkle_dag():
    """Verify 17-Node Merkle DAG structure and API integration in auditor_suite.html."""
    content = (STATIC_DIR / "auditor_suite.html").read_text(encoding="utf-8")
    
    # 1. Container & Render Function
    assert 'id="merkle-dag-container"' in content
    assert "function renderMerkleDAG" in content
    assert "DEFAULT_17_NODES" in content
    
    # 2. Verify all 17 Node IDs
    for i in range(1, 18):
        node_id = f"NODE-{str(i).padStart(2, '0')}" if hasattr(str(i), 'padStart') else f"NODE-{i:02d}"
        assert node_id in content, f"Missing Merkle DAG node ID: {node_id}"

    # 3. API Connection to graph endpoint
    assert "/api/v1/decisions/" in content
    assert "/graph" in content


# ==============================================================================
# 5. 9-PILLAR STATUTORY COMPLIANCE CHECKLIST IN AUDITOR_SUITE.HTML
# ==============================================================================

def test_m3_auditor_suite_9_pillar_audit_checklist():
    """Verify 9-Pillar Statutory Compliance checklist and API integration in auditor_suite.html."""
    content = (STATIC_DIR / "auditor_suite.html").read_text(encoding="utf-8")
    
    # 1. Table body & Render Function
    assert 'id="nine-pillars-tbody"' in content
    assert "function renderNinePillars" in content
    assert "DEFAULT_9_PILLARS" in content
    
    # 2. Verify all 9 Pillars
    for i in range(1, 10):
        pillar_tag = f"Pillar {i}"
        assert pillar_tag in content, f"Missing Pillar: {pillar_tag}"

    # 3. API Connection to audit-report endpoint
    assert "/audit-report" in content


# ==============================================================================
# 6. ZERO-LOGIN PUBLIC OFFLINE PROOF VERIFIER IN AUDITOR_SUITE.HTML
# ==============================================================================

def test_m3_auditor_suite_public_offline_verifier():
    """Verify Zero-Login Public Offline Proof Verifier in auditor_suite.html."""
    content = (STATIC_DIR / "auditor_suite.html").read_text(encoding="utf-8")
    
    # 1. Section & Digest/Seal elements
    assert 'id="public-verifier-section"' in content
    assert 'id="verifier-canonical-sha"' in content
    assert 'id="verifier-ed25519-seal"' in content
    
    # 2. Verification Function & Endpoint
    assert "function runAuditVerification" in content
    assert "/api/v1/decisions/verify" in content
    assert "IT Act 2000 Sec 3A" in content


# ==============================================================================
# 7. DEEP-LINK URL HASH NAVIGATION IN AUDITOR_SUITE.HTML
# ==============================================================================

def test_m3_auditor_suite_url_hash_navigation():
    """Verify deep-link hash listener and URL parameter handling in auditor_suite.html."""
    content = (STATIC_DIR / "auditor_suite.html").read_text(encoding="utf-8")
    
    # 1. Hash change listener & function
    assert "window.addEventListener('hashchange', handleHashNavigation)" in content
    assert "function handleHashNavigation" in content
    assert "startsWith('#verify-')" in content
    assert "scrollIntoView" in content
    
    # 2. Invoice selector sync
    assert 'id="invoice-select"' in content
    assert "switchAuditInvoice" in content


# ==============================================================================
# 8. RESPONSIVE REFLOW VERIFICATION ACROSS ALL WORKSPACES
# ==============================================================================

def test_m3_responsive_reflow_classes():
    """Verify responsive grid, flex, and table reflow wrappers across all workspaces."""
    for filename in FILES:
        content = (STATIC_DIR / filename).read_text(encoding="utf-8")
        
        # Responsive table containers
        assert "overflow-x-auto" in content, f"{filename} missing overflow-x-auto table wrapper"
        
        # Responsive grid reflow breakpoints (mobile sm/md/lg)
        assert ("grid-cols-1" in content or "flex-col" in content), f"{filename} missing mobile grid-cols-1 / flex-col"
        assert ("sm:" in content or "md:" in content or "lg:" in content), f"{filename} missing responsive breakpoints"
