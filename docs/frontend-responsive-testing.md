# Frontend Responsive & End-to-End Testing Documentation

## Overview
This document details the frontend testing architecture, responsive layout mechanisms, maker-checker segregation of duties (SoD), and duplicate payment protections for the **Autonomous AP & Statutory Treasury Cockpit**.

---

## 1. Architecture & Design Principles

### Single Vanilla JS & Tailwind Architecture
The application uses vanilla JavaScript with Tailwind CSS utility classes and HTML5 Web Components/Native Dialogs. No heavy JS frameworks (React, Vue, Angular) are loaded, ensuring lightning-fast initial load times and predictable browser execution.

### Dual Container Responsive Breakpoints
Data grids dynamically adapt between desktop and mobile viewport form factors:
- **Desktop (>= 1024px, `lg` breakpoint)**: Full 6-column dense data table (`<div class="hidden lg:block overflow-x-auto">`).
- **Tablet / Mobile (< 1024px)**: Responsive multi-line cards (`<div class="grid grid-cols-1 md:grid-cols-2 gap-3 lg:hidden" id="invoices-card-list">`).
- **Single Source of Truth**: Both table and card layouts are rendered from the same JavaScript data array (`GLOBAL_DECISIONS`, `ALL_VENDORS`, `AUDIT_DECISIONS`).

---

## 2. Testing Framework & Pytest-Playwright Setup

### Separation of Dependencies
- **Production (`requirements.txt`)**: Production runtime packages for Cloud Run (FastAPI, uvicorn, pydantic, google-cloud libraries). No test libraries or browser engines.
- **Development & CI (`requirements-dev.txt`)**: Contains `-r requirements.txt`, `pytest`, `pytest-playwright`, `pytest-base-url`, and pinned `playwright==1.62.0`.

### Deterministic Local Server Fixture
Playwright tests do not hit production networks. In `tests/playwright/conftest.py`, a session-scoped fixture starts `uvicorn main:app` on `127.0.0.1:4173`, conducts healthcheck polling against `/docs`, and terminates cleanly upon suite completion.

### Parameterized Viewport Fixtures
- **Desktop**: 1280 x 800
- **Tablet**: 768 x 1024
- **Mobile**: 375 x 667

---

## 3. Test Suites

| Test Module | Primary Assertions |
|-------------|-------------------|
| `test_responsive.py` | Validates desktop table visibility at 1280px, mobile card visibility at 768px and 375px; captures 3 baseline reference screenshots in `artifacts/screenshots/`. |
| `test_accessibility.py` | Asserts skip-to-content landmark `#main-content`, zero positive `tabindex` anti-patterns, ARIA dialog labeling (`aria-labelledby`, `aria-describedby`). |
| `test_exceptions.py` | Asserts Maker-Checker Segregation of Duties across isolated browser contexts (AP Clerk vs Treasury Controller). |
| `test_payment_release.py` | Asserts 3-level duplicate payment prevention: UI button disable on click, network idempotency header token, and backend idempotency caching. |
| `test_invoice_review.py` | Asserts light KPI enterprise cards and 4-step financial waterfall calculation. |
| `test_ingestion.py` | Asserts drag-and-drop document upload controls. |

---

## 4. Execution Commands

### Run Fast Backend Unit & Integration Tests (No Browser)
```bash
pytest -q -m "not playwright"
```

### Run Playwright Browser Suite
```bash
# Windows Batch Helper
scripts\run_playwright_tests.bat

# Cross-platform Shell Script
./scripts/run_playwright_tests.sh

# Direct Pytest CLI
pytest -q -m playwright --tracing=retain-on-failure --screenshot=only-on-failure --output=artifacts/playwright
```

### Golden Reference Screenshots
Screenshots are saved deterministically to:
- `artifacts/screenshots/desktop_dashboard_1280.png`
- `artifacts/screenshots/tablet_dashboard_768.png`
- `artifacts/screenshots/mobile_dashboard_375.png`
