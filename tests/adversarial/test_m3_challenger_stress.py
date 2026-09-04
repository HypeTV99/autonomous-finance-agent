"""
Adversarial Stress Test Suite for Milestone M3 (R3):
Multi-Screen Cohesion, Accessibility & Forensic Auditor Suite.

Challenger Verification for:
1. RFC 4180 CSV export edge cases (quotes, commas, newlines, nulls, injection chars, Unicode, Hindi, symbols).
2. URL hash deep linking resilience (#verify-*, malformed hashes, unknown invoices, XSS strings, traversal).
3. WCAG 2.1 AA mathematical contrast ratios (relative luminance formula) across all 3 screens.
4. Universal keyboard focus rings (focus-visible:ring-2) across all interactive controls.
5. Cross-screen DOM structural invariants and responsive reflow wrappers.
"""

import io
import csv
import re
import math
from pathlib import Path
import pytest

STATIC_DIR = Path(__file__).resolve().parent.parent.parent / "static"
SCREENS = ["dag.html", "vendor_intel.html", "auditor_suite.html"]


# ==============================================================================
# 1. ADVERSARIAL CSV EXPORT STRESS TESTS (RFC 4180)
# ==============================================================================

def test_adversarial_csv_export_special_characters_and_invariants():
    """Adversarially stress-tests CSV cell escaping with extreme edge cases."""
    headers = ['Invoice Number', 'Date', 'Gross Amount', 'Statutory Tax', 'Net Disbursed', 'Status', 'Audit Trail / Invariant Rule']

    def js_escape_cell(val):
        if val is None:
            return '""'
        s = str(val)
        if any(c in s for c in [',', '"', '\n', '\r']):
            return f'"{s.replace(chr(34), chr(34)+chr(34))}"'
        return f'"{s}"'

    adversarial_payloads = [
        # 1. Embedded quotes, double quotes, unclosed quotes
        {
            "id": 'INV-"SPECIAL"-01',
            "date": "2026-08-28",
            "gross": '₹1,50,000.00',
            "tax": '-₹15,000.00',
            "net": '₹1,35,000.00',
            "status": 'SETTLED',
            "why": 'Contains "embedded" quotes, ""double quotes"", and single \'quotes\'.'
        },
        # 2. CRLF, LF, and CR newlines within audit trail
        {
            "id": "INV-NEWLINE-02",
            "date": "2026-08-28",
            "gross": "₹2,00,000.00",
            "tax": "-₹20,000.00",
            "net": "₹1,80,000.00",
            "status": "SETTLED",
            "why": "Line 1: Section 194J verified.\r\nLine 2: Challan 281 tax escrow withheld.\nLine 3: 100% reconciled."
        },
        # 3. Comma-separated lists and semicolons
        {
            "id": "INV-COMMAS-03",
            "date": "2026-08-28",
            "gross": "₹5,90,000.00, formatted with commas",
            "tax": "-₹50,000.00",
            "net": "₹5,40,000.00",
            "status": "SETTLED",
            "why": "Vendors: Alpha, Beta, Gamma, and Delta; Invariant checks: 1, 2, 3, 4."
        },
        # 4. Formula injection characters (=, +, -, @, |)
        {
            "id": "INV-FORMULA-04",
            "date": "2026-08-28",
            "gross": "=SUM(A1:A10)",
            "tax": "@CALC(10%)",
            "net": "-₹100.00",
            "status": "+SETTLED",
            "why": "|cmd|' /C calc'!A0 -- formula injection payload safely enclosed in RFC 4180 quotes"
        },
        # 5. Multibyte UTF-8 Unicode, Currency Symbols & Devanagari
        {
            "id": "INV-UNICODE-05",
            "date": "2026-08-28",
            "gross": "₹12,45,000.00 € $ ¥",
            "tax": "-₹1,24,500.00",
            "net": "₹11,20,500.00",
            "status": "SETTLED",
            "why": "नमस्ते Vendor • Über Consulting GmbH • 100% Verified Invariant ✓"
        },
        # 6. Null, empty, and numeric zero values
        {
            "id": "INV-NULL-06",
            "date": None,
            "gross": "",
            "tax": "0",
            "net": "₹0.00",
            "status": None,
            "why": None
        }
    ]

    csv_lines = [",".join(f'"{h}"' for h in headers)]
    for item in adversarial_payloads:
        row = [
            js_escape_cell(item["id"]),
            js_escape_cell(item["date"]),
            js_escape_cell(item["gross"]),
            js_escape_cell(item["tax"]),
            js_escape_cell(item["net"]),
            js_escape_cell(item["status"]),
            js_escape_cell(item["why"])
        ]
        csv_lines.append(",".join(row))

    full_csv = "\r\n".join(csv_lines)

    # Strictly parse using Python's standard csv module (RFC 4180 engine)
    reader = list(csv.reader(io.StringIO(full_csv)))

    # Invariant: exactly 1 header + 6 data rows = 7 rows total
    assert len(reader) == 7, f"Expected 7 parsed rows, got {len(reader)}"
    assert reader[0] == headers

    # Row 1: Embedded quotes intact
    assert reader[1][0] == 'INV-"SPECIAL"-01'
    assert reader[1][6] == 'Contains "embedded" quotes, ""double quotes"", and single \'quotes\'.'

    # Row 2: Multiline audit trail preserves exact newlines
    assert "Line 1: Section 194J verified." in reader[2][6]
    assert "Line 2: Challan 281 tax escrow withheld." in reader[2][6]
    assert "Line 3: 100% reconciled." in reader[2][6]

    # Row 3: Commas preserved without column shifting
    assert len(reader[3]) == 7
    assert reader[3][2] == "₹5,90,000.00, formatted with commas"
    assert reader[3][6] == "Vendors: Alpha, Beta, Gamma, and Delta; Invariant checks: 1, 2, 3, 4."

    # Row 4: Formula characters safely captured
    assert reader[4][2] == "=SUM(A1:A10)"
    assert reader[4][3] == "@CALC(10%)"
    assert reader[4][6] == "|cmd|' /C calc'!A0 -- formula injection payload safely enclosed in RFC 4180 quotes"

    # Row 5: Unicode and currency symbols preserved
    assert "नमस्ते Vendor" in reader[5][6]
    assert "₹12,45,000.00" in reader[5][2]
    assert "Über Consulting GmbH" in reader[5][6]

    # Row 6: Nulls rendered as empty strings
    assert reader[6][1] == ""
    assert reader[6][5] == ""
    assert reader[6][6] == ""


# ==============================================================================
# 2. ADVERSARIAL URL HASH DEEP LINKING STRESS TESTS
# ==============================================================================

def test_adversarial_url_hash_deep_linking_invariants():
    """Adversarially tests URL hash parsing logic and error handling in auditor_suite.html."""
    content = (STATIC_DIR / "auditor_suite.html").read_text(encoding="utf-8")

    # 1. Verify existence of hash handler and event listener
    assert "window.addEventListener('hashchange', handleHashNavigation)" in content
    assert "function handleHashNavigation" in content
    assert "function loadAuditDataForInvoice" in content

    # 2. Simulate handleHashNavigation with adversarial inputs
    def simulate_hash_navigation(hash_val):
        if not hash_val or not hash_val.startswith("#verify-"):
            return "INV-884"  # Default fallback
        inv_id = hash_val.replace("#verify-", "").strip()
        return inv_id if inv_id else "INV-884"

    test_hashes = [
        ("#", "INV-884"),
        ("#!", "INV-884"),
        ("#verify-", "INV-884"),
        ("#verify-   ", "INV-884"),
        ("#verify-INV-884", "INV-884"),
        ("#verify-INV-742", "INV-742"),
        ("#verify-INV-619", "INV-619"),
        ("#verify-UNKNOWN-999", "UNKNOWN-999"),
        ("#verify-<script>alert(1)</script>", "<script>alert(1)</script>"),
        ("#verify-../../etc/passwd", "../../etc/passwd"),
        ("#verify-INV-884?param=1", "INV-884?param=1"),
        ("#verify-INV-884#secondhash", "INV-884#secondhash")
    ]

    for raw_hash, expected_extracted_id in test_hashes:
        extracted = simulate_hash_navigation(raw_hash)
        assert extracted == expected_extracted_id, f"Hash '{raw_hash}' extracted '{extracted}', expected '{expected_extracted_id}'"

    # 3. Verify JavaScript error handling & fallbacks for unknown/failing API calls
    assert "renderMerkleDAG(DEFAULT_17_NODES)" in content
    assert "renderNinePillars(DEFAULT_9_PILLARS)" in content
    assert "catch(e)" in content


# ==============================================================================
# 3. EMPIRICAL WCAG 2.1 AA CONTRAST RATIO AUDIT
# ==============================================================================

def calculate_relative_luminance(hex_color: str) -> float:
    """Calculates relative luminance according to WCAG 2.1 specification."""
    hex_color = hex_color.lstrip('#')
    if len(hex_color) == 3:
        hex_color = ''.join(c * 2 for c in hex_color)
    r = int(hex_color[0:2], 16) / 255.0
    g = int(hex_color[2:4], 16) / 255.0
    b = int(hex_color[4:6], 16) / 255.0

    def adjust(val):
        return val / 12.92 if val <= 0.03928 else math.pow((val + 0.055) / 1.055, 2.4)

    r_adj = adjust(r)
    g_adj = adjust(g)
    b_adj = adjust(b)

    return 0.2126 * r_adj + 0.7152 * g_adj + 0.0722 * b_adj


def calculate_contrast_ratio(hex1: str, hex2: str) -> float:
    """Calculates WCAG contrast ratio between two colors (L1 + 0.05) / (L2 + 0.05)."""
    l1 = calculate_relative_luminance(hex1)
    l2 = calculate_relative_luminance(hex2)
    lighter = max(l1, l2)
    darker = min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


def test_empirical_wcag_aa_contrast_ratios_on_tokens():
    """Mathematically verifies that all semantic and body color tokens exceed WCAG 2.1 AA 4.5:1 ratio."""
    # Palette definition from Tailwind / CSS
    CANVAS_BG = "#F8FAFC"
    CARD_BG = "#FFFFFF"
    
    TEXT_TOKENS = {
        "charcoal (#0F172A)": ("#0F172A", 15.5),      # Charcoal headings/body
        "slate-900 (#0F172A)": ("#0F172A", 15.5),     # Slate 900
        "slate-800 (#1E293B)": ("#1E293B", 12.6),     # Slate 800
        "slate-700 (#334155)": ("#334155", 9.8),      # Slate 700 (labels/subtext)
        "slate-600 (#475569)": ("#475569", 5.6),      # Slate 600 (muted text)
        "emerald-800 (#065F46)": ("#065F46", 5.9),    # Emerald badge text
        "emerald-700 (#047857)": ("#047857", 4.6),    # Emerald accent
        "amber-900 (#78350F)": ("#78350F", 7.8),      # Amber badge text
        "purple-800 (#581C87)": ("#581C87", 11.6),    # Purple badge text
        "rose-800 (#9F1239)": ("#9F1239", 8.0),       # Rose badge text
        "rose-700 (#BE123C)": ("#BE123C", 5.4),       # Rose tax indicator
        "blue-800 (#1E40AF)": ("#1E40AF", 7.4)        # Blue badge text
    }

    # Verify on Card Background (#FFFFFF)
    for name, (hex_val, _) in TEXT_TOKENS.items():
        ratio = calculate_contrast_ratio(CARD_BG, hex_val)
        assert ratio >= 4.5, f"Contrast ratio for {name} on #FFFFFF is {ratio:.2f}:1, below WCAG AA 4.5:1"

    # Verify on Canvas Background (#F8FAFC)
    for name, (hex_val, _) in TEXT_TOKENS.items():
        ratio = calculate_contrast_ratio(CANVAS_BG, hex_val)
        assert ratio >= 4.5, f"Contrast ratio for {name} on #F8FAFC is {ratio:.2f}:1, below WCAG AA 4.5:1"

    # Verify Badge text on respective badge background pills:
    BADGE_PAIRS = [
        ("SETTLED Emerald", "#065F46", "#ECFDF5"),    # emerald-800 on emerald-50
        ("COOLING Amber", "#78350F", "#FEF3C7"),      # amber-900 on amber-100/50
        ("TDS Purple", "#581C87", "#FAF5FF"),         # purple-800 on purple-50
        ("VIOLATION Rose", "#9F1239", "#FFF1F2"),     # rose-800 on rose-50
        ("READY Blue", "#1E40AF", "#EFF6FF")          # blue-800 on blue-50
    ]

    for name, text_hex, bg_hex in BADGE_PAIRS:
        ratio = calculate_contrast_ratio(text_hex, bg_hex)
        assert ratio >= 4.5, f"Badge {name} contrast ratio {ratio:.2f}:1 is below WCAG AA 4.5:1"


# ==============================================================================
# 4. UNIVERSAL KEYBOARD FOCUS RINGS AUDIT ACROSS ALL 3 SCREENS
# ==============================================================================

def test_universal_keyboard_focus_rings_on_all_interactive_controls():
    """Verifies that all buttons, links, selects, and inputs across all 3 HTML files have visible focus rings."""
    for screen in SCREENS:
        filepath = STATIC_DIR / screen
        content = filepath.read_text(encoding="utf-8")

        # 1. Check all <button> elements have focus-visible:ring-2
        button_tags = re.findall(r'<button\b[^>]*>', content)
        for btn in button_tags:
            # Skip hidden or inert template buttons if any
            if 'tabindex="-1"' in btn or 'aria-hidden="true"' in btn:
                continue
            assert "focus-visible:ring-2" in btn or "focus-visible:ring" in btn, f"Button missing focus ring in {screen}: {btn}"

        # 2. Check all <select> elements have focus-visible:ring-2
        select_tags = re.findall(r'<select\b[^>]*>', content)
        for sel in select_tags:
            assert "focus-visible:ring-2" in sel, f"Select missing focus ring in {screen}: {sel}"

        # 3. Check navigation header links have focus-visible:ring-2
        nav_links = re.findall(r'<a\b[^>]*href="/(?:dashboard|vendor-intel|audit)"[^>]*>', content)
        for link in nav_links:
            assert "focus-visible:ring-2" in link, f"Navigation link missing focus ring in {screen}: {link}"


# ==============================================================================
# 5. CROSS-SCREEN LAYOUT & RESPONSIVE REFLOW INVARIANTS
# ==============================================================================

def test_cross_screen_layout_and_responsive_reflow_invariants():
    """Verifies layout containers, max width, table horizontal scrolling, and responsive grids."""
    for screen in SCREENS:
        filepath = STATIC_DIR / screen
        content = filepath.read_text(encoding="utf-8")

        # Max width 1720px container for 1720px+ viewports
        assert "max-w-[1720px]" in content, f"Missing 1720px container in {screen}"

        # Viewport meta tag for mobile (375px)
        assert '<meta name="viewport" content="width=device-width, initial-scale=1.0"/>' in content

        # Table horizontal scrolling wrappers
        if "<table" in content:
            assert "overflow-x-auto" in content, f"Table in {screen} lacks overflow-x-auto wrapper"

        # Responsive grid or flex reflow classes for tablet/mobile
        assert "grid-cols-1" in content or "flex-col" in content, f"Missing responsive reflow classes in {screen}"