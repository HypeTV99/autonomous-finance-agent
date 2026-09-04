# Yire: Autonomous AP & Statutory Treasury Engine

An autonomous enterprise Accounts Payable (AP) and statutory treasury engine featuring real-time 3-way matching, GSTIN filing hygiene verification, Section 206AB higher TDS deduction defense, maker-checker segregation of duties (SoD), and cryptographically verified audit trails.

---

## 🏛️ Architecture Highlights

- **Dual-View Responsive Interface**: Dense, high-speed 6-column data grid on desktop viewports (`>= 1024px`), transforming seamlessly into accessible touch-friendly card units on tablet and mobile viewports (`< 1024px`).
- **Maker-Checker Segregation of Duties**: Distinct operational personas (`ROLE_AP_CLERK` for document ingestion, `ROLE_CONTROLLER` for review and exception resolution, `ROLE_TREASURER` for wire release).
- **Three-Level Duplicate Payment Protection**:
  1. **UI Layer**: Immediate button disable and `aria-busy` state upon submission.
  2. **Network Contract**: Client-generated `X-Idempotency-Key` or idempotency token.
  3. **Backend Engine**: Atomic database-level verification caching identical settlement results without double payouts.
- **Cryptographic Audit Ledger**: Invariant attestation using RFC 8785 Canonical JSON and Ed25519 hardware key signatures.

---

## 🧪 Testing Guide

The testing architecture strictly isolates production dependencies (`requirements.txt`) from local and CI testing tools (`requirements-dev.txt`).

### 1. Fast Backend & Integration Tests (No Browser)
Run all 113+ backend unit, validation, and double-entry integration tests:
```bash
pytest -q -m "not playwright"
```

### 2. Playwright UI & Responsive Tests
Run end-to-end browser tests across desktop (1280px), tablet (768px), and mobile (375px) viewports:

**On Windows:**
```cmd
scripts\run_playwright_tests.bat
```

**On Linux / macOS:**
```bash
./scripts/run_playwright_tests.sh
```

**Direct Pytest CLI:**
```bash
pytest -q -m playwright --tracing=retain-on-failure --screenshot=only-on-failure --output=artifacts/playwright
```

### 3. Golden Responsive Reference Screenshots
Automated viewport tests capture and persist baseline screenshots in:
- `artifacts/screenshots/desktop_dashboard_1280.png`
- `artifacts/screenshots/tablet_dashboard_768.png`
- `artifacts/screenshots/mobile_dashboard_375.png`

For full frontend architecture and testing details, see [docs/frontend-responsive-testing.md](docs/frontend-responsive-testing.md).
