# Codebase Conventions & Standards

## Architectural Rules
1. **Facade & Services Parity**: Any logic updated in `services/*.py` must also be kept synchronized in `compliance_engine.py` to preserve full backward compatibility with existing tests and imports.
2. **Deterministic Schemas**: All responses from API endpoints must strictly validate against `schemas.py` (`Pydantic`).
3. **Cryptographic Sealing**: Key pairs and KMS anchors must never leak private keys; public keys are verified offline on `/verify-portal`.
4. **UI Styling**: All HTML views reside in `static/` and are routed via `routers/ui.py`. Do NOT change colors or styles unless requested.

## Error Handling & Status Codes
- All decision points return explicit deterministic states: `AUTO_APPROVED`, `CRITICAL_RISK_HOLD`, `RATE_VARIANCE_BLOCKED`, `CONTROLLER_REVIEW_REQUIRED`, `AUTO_APPROVED_WITH_SIGNOFF`.
- Simulation results return `CounterfactualSimulationResult` with structured `downstream_causal_deltas`.
