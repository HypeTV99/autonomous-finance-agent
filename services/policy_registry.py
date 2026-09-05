from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
import hashlib
import json
from typing import Any, Dict, List, Optional, Tuple, Union
from pydantic import BaseModel, ConfigDict, Field


class PolicyType(str, Enum):
    MATCHING_POLICY = "MATCHING_POLICY"
    TAX_POLICY = "TAX_POLICY"
    PAYMENT_POLICY = "PAYMENT_POLICY"
    RETENTION_POLICY = "RETENTION_POLICY"
    TOLERANCE_POLICY = "TOLERANCE_POLICY"
    DISCOUNT_POLICY = "DISCOUNT_POLICY"
    ACCOUNTING_POLICY = "ACCOUNTING_POLICY"
    RISK_POLICY = "RISK_POLICY"


class ImmutablePolicyMutationError(ValueError):
    """Raised when an attempt is made to mutate or overwrite an existing registered policy version."""
    pass


class PolicyNotFoundError(KeyError):
    """Raised when a requested policy type and version cannot be resolved in the registry."""
    pass


class PolicyDefinition(BaseModel):
    model_config = ConfigDict(frozen=True)

    policy_type: PolicyType
    version: str
    effective_from: str
    effective_until: Optional[str] = None
    rules_digest: str
    rules_payload: Dict[str, Any]
    is_immutable: bool = True
    description: Optional[str] = None


class EnterprisePolicyRegistry:
    """
    Centralized, cryptographically-anchored registry for enterprise AP policies.
    Guarantees that policy versions are immutable once registered.
    """
    _POLICIES: Dict[Tuple[str, str], PolicyDefinition] = {}

    @classmethod
    def compute_rules_digest(cls, rules: Dict[str, Any]) -> str:
        """Computes deterministic SHA-256 digest over canonical JSON of rules payload."""
        canonical_json = json.dumps(rules, sort_keys=True, separators=(',', ':'), ensure_ascii=False)
        return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()

    @classmethod
    def register_policy(cls, policy_def: PolicyDefinition) -> None:
        """
        Registers an immutable policy version.
        Raises ImmutablePolicyMutationError if an existing policy version has different rules.
        """
        key = (policy_def.policy_type.value, policy_def.version)
        if key in cls._POLICIES:
            existing = cls._POLICIES[key]
            if existing.rules_digest == policy_def.rules_digest and existing.rules_payload == policy_def.rules_payload:
                # Idempotent re-registration of identical policy version
                return
            raise ImmutablePolicyMutationError(
                f"Cannot mutate registered immutable policy '{policy_def.policy_type.value}' "
                f"version '{policy_def.version}'. Existing digest: {existing.rules_digest}, "
                f"Attempted digest: {policy_def.rules_digest}. Policies must be versioned monotonically."
            )
        cls._POLICIES[key] = policy_def

    @classmethod
    def get_policy(cls, policy_type: Union[PolicyType, str], version: str) -> PolicyDefinition:
        """Retrieves a specific policy type and version. Raises PolicyNotFoundError if absent."""
        p_type_val = policy_type.value if isinstance(policy_type, PolicyType) else str(policy_type)
        key = (p_type_val, version)
        if key not in cls._POLICIES:
            raise PolicyNotFoundError(f"Policy '{p_type_val}' version '{version}' not found in registry.")
        return cls._POLICIES[key]

    @classmethod
    def resolve_policy_at(
        cls,
        policy_type: Union[PolicyType, str],
        timestamp_iso: Optional[str] = None
    ) -> Optional[PolicyDefinition]:
        """
        Resolves the policy in force at a given historical timestamp.
        Defaults to current UTC timestamp if omitted.
        """
        p_type_val = policy_type.value if isinstance(policy_type, PolicyType) else str(policy_type)
        target_ts = timestamp_iso or datetime.now(timezone.utc).isoformat()

        candidate_policies: List[PolicyDefinition] = []
        for (pt, _ver), pdef in cls._POLICIES.items():
            if pt == p_type_val:
                if pdef.effective_from <= target_ts:
                    if pdef.effective_until is None or target_ts <= pdef.effective_until:
                        candidate_policies.append(pdef)

        if not candidate_policies:
            # Fallback to latest registered version for that policy type
            matching = [pdef for (pt, _), pdef in cls._POLICIES.items() if pt == p_type_val]
            return matching[-1] if matching else None

        # Sort by effective_from descending, pick the most specific active one
        candidate_policies.sort(key=lambda p: p.effective_from, reverse=True)
        return candidate_policies[0]

    @classmethod
    def resolve_decision_policy(
        cls,
        policy_type: Union[PolicyType, str],
        explicit_version: Optional[str] = None,
        decision_timestamp: Optional[str] = None,
    ) -> PolicyDefinition:
        """
        Historical Decision Policy Resolution:
        - Primary Evidence: If an explicit policy version was stored at decision time (and is not
          unversioned / missing), that exact immutable version is resolved directly.
        - Fallback / New Decisions: If explicit_version is absent or 'LEGACY_UNVERSIONED', resolves
          based on decision_timestamp via resolve_policy_at.
        This invariant prevents retroactive policy misattribution during historical replay.
        """
        if explicit_version and explicit_version not in ("LEGACY_UNVERSIONED", "", "None"):
            try:
                return cls.get_policy(policy_type, explicit_version)
            except PolicyNotFoundError:
                pass
        resolved = cls.resolve_policy_at(policy_type, decision_timestamp)
        if not resolved:
            raise PolicyNotFoundError(f"Cannot resolve policy '{policy_type}' at timestamp '{decision_timestamp}'")
        return resolved

    @classmethod
    def list_policies(cls) -> List[PolicyDefinition]:
        """Returns all registered policy definitions."""
        return list(cls._POLICIES.values())

    @classmethod
    def reset_registry(cls) -> None:
        """Test fixture helper to reset policies back to seed defaults."""
        cls._POLICIES.clear()
        cls._seed_default_policies()

    @classmethod
    def _seed_default_policies(cls) -> None:
        """Seeds canonical 2026.1 versions of enterprise AP policies."""
        seeds = [
            (
                PolicyType.MATCHING_POLICY,
                "2026.1",
                {
                    "mode": "THREE_WAY_CUMULATIVE",
                    "require_lineage": True,
                    "po_check": True,
                    "grn_check": True,
                    "quantity_tolerance_pct": "0.0000",
                    "price_tolerance_pct": "0.0000"
                },
                "Canonical 3-way cumulative matching policy"
            ),
            (
                PolicyType.TAX_POLICY,
                "2026.1",
                {
                    "tds_framework": "INCOME_TAX_ACT_2025",
                    "gstin_verification": "MANDATORY_EVIDENCE_GSTR2B",
                    "tds_threshold_enforcement": "CUMULATIVE_PAN_FY",
                    "lower_deduction_cert_validation": True
                },
                "Statutory dual-act date-aware tax compliance policy"
            ),
            (
                PolicyType.PAYMENT_POLICY,
                "2026.1",
                {
                    "idempotency_enforcement": "STRICT_PAYMENT_INTENT",
                    "cooling_off_period_hours": 48,
                    "maximum_single_payout_inr": "10000000.00",
                    "zero_payout_bypass": True,
                    "rail_routing_policy": {
                        "threshold_paise": 20000000,
                        "high_value_mode": "NEFT",
                        "low_value_mode": "IMPS",
                        "default_purpose": "vendor bill",
                        "source": "Treasury AP Policy v2026.1 (Historical)"
                    }
                },
                "Idempotent treasury disbursement, rail routing & cooling-off policy (Historical)"
            ),
            (
                PolicyType.PAYMENT_POLICY,
                "2026.2",
                {
                    "idempotency_enforcement": "STRICT_PAYMENT_INTENT",
                    "cooling_off_period_hours": 48,
                    "maximum_single_payout_inr": "10000000.00",
                    "zero_payout_bypass": True,
                    "provider_capability": {
                        "imps_maximum_limit_paise": 50000000,
                        "neft_supported": True,
                        "rtgs_supported": True,
                        "source": "NPCI IMPS limit (revised to ₹5 Lakh in Oct 2021) & RazorpayX documentation"
                    },
                    "rail_routing_policy": {
                        "threshold_paise": 20000000,
                        "high_value_mode": "NEFT",
                        "low_value_mode": "IMPS",
                        "default_purpose": "vendor bill",
                        "policy_classification": "INTERNAL_TREASURY_PAYMENT_RAIL_POLICY",
                        "rationale": "Internal treasury routing and bank rail fee optimization. Payouts >= ₹2,00,000 route via NEFT for batch processing and lower per-transaction banking fees; payouts < ₹2,00,000 route via IMPS for immediate vendor liquidity. This threshold is an internal company preference, NOT an NPCI regulatory ceiling.",
                        "source": "Corporate Treasury AP Policy v2026.2"
                    }
                },
                "Idempotent treasury disbursement, rail routing & cooling-off policy (Internal Treasury Standard)"
            ),
            (
                PolicyType.RETENTION_POLICY,
                "2026.1",
                {
                    "gstr2b_pending_retention_pct": "100.0000",
                    "contractual_milestone_hold_allowed": True,
                    "escrow_account": "LIAB-2150"
                },
                "Statutory and contractual retention escrow policy"
            ),
            (
                PolicyType.TOLERANCE_POLICY,
                "2026.1",
                {
                    "unit_price_tolerance_absolute_inr": "0.00",
                    "cumulative_quantity_overbill_allowed": False,
                    "rounding_diff_max_inr": "0.02"
                },
                "Zero-tolerance cumulative allocation and price variance policy"
            ),
            (
                PolicyType.DISCOUNT_POLICY,
                "2026.1",
                {
                    "annualized_rate_calculation": "EFFECTIVE_AND_SIMPLE",
                    "cost_of_capital_pct": "12.0000",
                    "liquidity_cost_pct": "2.0000",
                    "min_net_benefit_inr": "100.00"
                },
                "Explainable dynamic discounting and APR/EAR evaluation policy"
            ),
            (
                PolicyType.ACCOUNTING_POLICY,
                "2026.1",
                {
                    "double_entry_exactness": "EXACT_ZERO_PAISA",
                    "rounding_account": "9990",
                    "posted_journal_immutability": True,
                    "reversal_workflow": "REVERSAL_AND_REPLACEMENT"
                },
                "Semantic double-entry and posted journal immutability policy"
            ),
            (
                PolicyType.RISK_POLICY,
                "2026.1",
                {
                    "bank_quarantine_hours": 48,
                    "amount_anomaly_multiplier": 3.0,
                    "max_weekly_invoice_velocity": 5,
                    "enforce_hitl_on_high_risk": True
                },
                "Continuous behavioral risk and cooling-window quarantine policy"
            ),
        ]

        for p_type, ver, rules, desc in seeds:
            digest = cls.compute_rules_digest(rules)
            eff_from = "2026-01-01T00:00:00Z"
            eff_until = None
            if p_type == PolicyType.PAYMENT_POLICY and ver == "2026.1":
                eff_until = "2026-09-04T22:00:00Z"
            elif p_type == PolicyType.PAYMENT_POLICY and ver == "2026.2":
                eff_from = "2026-09-04T22:00:00Z"
            p_def = PolicyDefinition(
                policy_type=p_type,
                version=ver,
                effective_from=eff_from,
                effective_until=eff_until,
                rules_digest=digest,
                rules_payload=rules,
                is_immutable=True,
                description=desc
            )
            cls._POLICIES[(p_type.value, ver)] = p_def


# Initialize seed policies on import
EnterprisePolicyRegistry._seed_default_policies()
