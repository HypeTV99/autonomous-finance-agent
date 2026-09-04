# YIRE Autonomous Finance Brain - Core Architecture

Autonomous, self-auditing financial engine for invoice ingestion, statutory Indian tax compliance (TDS), 3-way PO/GRN matching, 48h bank takeover cooling, Ed25519 asymmetric cryptographic KMS sealing, and RazorpayX payout execution.

## Memory Graph
- For languages, frameworks, runtime dependencies, and Cloud Run specs: `mem:tech_stack`
- For terminal commands, test runners, and deployment execution on Windows: `mem:suggested_commands`
- For strict coding standards, invariant enforcement, brand rules, and facades: `mem:conventions`
- For verification checklist, pytest suites, and post-task audit procedures: `mem:task_completion`

## Key Invariants
1. **Brand Identity**: Brand name is strictly "Yire". Never change or propose color palette modifications.
2. **Autonomous Execution**: Never block for non-critical confirmations; execute end-to-end.
3. **9 Non-Negotiable Financial Invariants**: Credit conservation, double-entry balance, rate cap ceilings (₹2,000/hr), 48h bank cooling, penal TDS floor (20% Sec 206AA).
4. **Architectural Split**: Monolithic engines are modularized into `services/` (`crypto`, `ledger`, `reconciliation`, `lineage`, `simulation`, `audit`, `learning`) and `routers/` with backward-compatible facades in `compliance_engine.py`.
