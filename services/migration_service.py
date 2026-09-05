from datetime import datetime, timezone
from decimal import Decimal
import logging
from typing import Any, Dict, List, Optional, Tuple

from firestore_store import FirestoreStateStore

logger = logging.getLogger("MigrationService")


class MigrationService:
    """
    Restart-Safe, Idempotent Data Migration Service (Prompt 11 Standard).
    Implements Expand-and-Contract lifecycle:
    - Phase A: Dual-read compatibility (code reads legacy + modern)
    - Phase B: New writes use modern representation
    - Phase C: Idempotent backfill with restart-safety
    - Phase D: Completeness verification
    - Historical records remain explicitly distinguishable (e.g. LEGACY_PRE_2026)
    """

    MIGRATION_TARGET_VERSION = "2026.1"

    def __init__(self, store: Optional[FirestoreStateStore] = None):
        self.store = store or FirestoreStateStore()

    @classmethod
    def migrate_payment_record(cls, record: Dict[str, Any]) -> Tuple[Dict[str, Any], bool]:
        """
        Idempotently migrates an existing payment intent or instruction record.
        Upgrades legacy amount aliases, derives payout_paise, and ensures versioning.
        """
        if record.get("is_migrated") and record.get("schema_version") == cls.MIGRATION_TARGET_VERSION:
            return record, False

        migrated = dict(record)

        # 1. Gross amount normalization
        gross = migrated.get("gross_subtotal") or migrated.get("gross_amount") or migrated.get("net_payout_amount") or "0.00"
        gross_dec = Decimal(str(gross))
        migrated["gross_subtotal"] = str(gross_dec)

        # 2. Net payout normalization
        net = (
            migrated.get("net_payout_amount") or
            migrated.get("settlement_amount") or
            migrated.get("approved_amount") or
            gross
        )
        net_dec = Decimal(str(net))
        migrated["net_payout_amount"] = str(net_dec)

        # 3. Payout paise calculation
        payout_paise = migrated.get("payout_paise")
        if payout_paise is None:
            migrated["payout_paise"] = int((net_dec * Decimal("100")).quantize(Decimal("1")))

        # 4. Zero payout hold flag
        if "requires_zero_payout_hold" not in migrated:
            migrated["requires_zero_payout_hold"] = (migrated["payout_paise"] < 100)

        # 5. Safe default metadata
        migrated.setdefault("currency", "INR")
        migrated.setdefault("version", 1)
        migrated.setdefault("environment", "SANDBOX")
        migrated.setdefault("tds_section", "NONE")
        migrated.setdefault("tds_withheld", "0.00")
        migrated.setdefault("applied_credits_total", "0.00")
        migrated.setdefault("tax_amount", "0.00")
        migrated.setdefault("vendor_pan", "PANNOTPROVIDED")
        migrated.setdefault("attempt_count", 0)

        # 6. Migration markers
        migrated["schema_version"] = cls.MIGRATION_TARGET_VERSION
        migrated["is_migrated"] = True
        migrated["migration_status"] = "MIGRATED_V2"
        migrated["migrated_at"] = datetime.now(timezone.utc).isoformat()

        return migrated, True

    @classmethod
    def migrate_credit_record(cls, record: Dict[str, Any]) -> Tuple[Dict[str, Any], bool]:
        """
        Idempotently migrates an open credit record from single available_balance
        into the 4-variable conservation model (original, available, reserved, consumed).
        """
        if record.get("is_migrated") and record.get("schema_version") == cls.MIGRATION_TARGET_VERSION:
            return record, False

        migrated = dict(record)

        avail = migrated.get("available_amount") or migrated.get("available_balance") or "0.00"
        avail_dec = Decimal(str(avail))
        orig_dec = Decimal(str(migrated.get("original_amount") or avail_dec))
        res_dec = Decimal(str(migrated.get("reserved_amount") or "0.00"))
        cons_dec = Decimal(str(migrated.get("consumed_amount") or "0.00"))

        migrated["original_amount"] = str(orig_dec)
        migrated["available_amount"] = str(avail_dec)
        migrated["reserved_amount"] = str(res_dec)
        migrated["consumed_amount"] = str(cons_dec)
        migrated["available_balance"] = str(avail_dec)

        migrated["schema_version"] = cls.MIGRATION_TARGET_VERSION
        migrated["is_migrated"] = True
        migrated["migration_status"] = "MIGRATED_V2"
        migrated["migrated_at"] = datetime.now(timezone.utc).isoformat()

        return migrated, True

    @classmethod
    def migrate_decision_record(cls, record: Dict[str, Any]) -> Tuple[Dict[str, Any], bool]:
        """
        Idempotently migrates a legacy decision record.
        Preserves historical unversioned distinction (LEGACY_PRE_2026) so old records
        never falsely claim modern 2026 policy attestation.
        """
        if record.get("is_migrated"):
            return record, False

        migrated = dict(record)

        # Distinguish historical records without policy versions
        is_historical = not bool(migrated.get("matching_policy_version"))
        legacy_tag = "LEGACY_PRE_2026" if is_historical else cls.MIGRATION_TARGET_VERSION

        migrated.setdefault("schema_version", legacy_tag)
        migrated.setdefault("matching_policy_version", legacy_tag)
        migrated.setdefault("tax_policy_version", legacy_tag)
        migrated.setdefault("payment_policy_version", legacy_tag)
        migrated.setdefault("retention_policy_version", legacy_tag)
        migrated.setdefault("tolerance_policy_version", legacy_tag)
        migrated.setdefault("discount_policy_version", legacy_tag)
        migrated.setdefault("accounting_policy_version", legacy_tag)
        migrated.setdefault("risk_policy_version", legacy_tag)

        migrated["is_migrated"] = True
        migrated["migration_status"] = "MIGRATED_V2"
        migrated["migrated_at"] = datetime.now(timezone.utc).isoformat()

        return migrated, True

    def run_full_migration(self, store: Optional[FirestoreStateStore] = None) -> Dict[str, Any]:
        """
        Executes an idempotent, restart-safe database migration across all core collections.
        Can be rerun or resumed after interruption without data corruption.
        """
        target_store = store or getattr(self, "store", None)
        if not target_store:
            target_store = FirestoreStateStore()
        return self._run_full_migration_impl(target_store)

    @classmethod
    def execute_migration(cls, store: FirestoreStateStore) -> Dict[str, Any]:
        return cls._run_full_migration_impl(store)

    @classmethod
    def _run_full_migration_impl(cls, store: FirestoreStateStore) -> Dict[str, Any]:
        stats = {
            "migrated_payments": 0,
            "payments_migrated": 0,
            "migrated_credits": 0,
            "credits_migrated": 0,
            "migrated_decisions": 0,
            "decisions_migrated": 0,
            "skipped_already_migrated": 0,
            "payments_already_v2": 0,
            "credits_already_v2": 0,
            "decisions_already_v2": 0,
            "status": "IN_PROGRESS"
        }

        # 1. Migrate Payment Intents
        if store._is_mock:
            intents = store._mock_db.get("payment_intents", {})
            for key, rec in list(intents.items()):
                migrated, changed = cls.migrate_payment_record(rec)
                if changed:
                    intents[key] = migrated
                    stats["migrated_payments"] += 1
                    stats["payments_migrated"] += 1
                else:
                    stats["skipped_already_migrated"] += 1
                    stats["payments_already_v2"] += 1
        else:
            docs = store.db.collection("payment_intents").stream()
            for doc in docs:
                data = doc.to_dict() or {}
                migrated, changed = cls.migrate_payment_record(data)
                if changed:
                    store.db.collection("payment_intents").document(doc.id).set(migrated, merge=True)
                    stats["migrated_payments"] += 1
                    stats["payments_migrated"] += 1
                else:
                    stats["skipped_already_migrated"] += 1
                    stats["payments_already_v2"] += 1

        # 2. Migrate Vendor Open Credits
        if store._is_mock:
            credits_map = store._mock_db.get("vendor_open_credits", {})
            for vendor_id, credit_list in list(credits_map.items()):
                updated_list = []
                for cred in credit_list:
                    c_dict = cred if isinstance(cred, dict) else cred.model_dump(mode="json")
                    migrated, changed = cls.migrate_credit_record(c_dict)
                    updated_list.append(migrated)
                    if changed:
                        stats["migrated_credits"] += 1
                        stats["credits_migrated"] += 1
                    else:
                        stats["skipped_already_migrated"] += 1
                        stats["credits_already_v2"] += 1
                credits_map[vendor_id] = updated_list
        else:
            docs = store.db.collection("vendor_open_credits").stream()
            for doc in docs:
                data = doc.to_dict() or {}
                credits = data.get("credits", [])
                updated = []
                for cred in credits:
                    migrated, changed = cls.migrate_credit_record(cred)
                    updated.append(migrated)
                    if changed:
                        stats["migrated_credits"] += 1
                        stats["credits_migrated"] += 1
                    else:
                        stats["skipped_already_migrated"] += 1
                        stats["credits_already_v2"] += 1
                store.db.collection("vendor_open_credits").document(doc.id).update({"credits": updated})

        # 3. Migrate Decision Records
        if store._is_mock:
            decisions = store._mock_db.get("immutable_decision_records", {})
            for dec_id, rec in list(decisions.items()):
                migrated, changed = cls.migrate_decision_record(rec)
                if changed:
                    decisions[dec_id] = migrated
                    stats["migrated_decisions"] += 1
                    stats["decisions_migrated"] += 1
                else:
                    stats["skipped_already_migrated"] += 1
                    stats["decisions_already_v2"] += 1
        else:
            docs = store.db.collection("immutable_decision_records").stream()
            for doc in docs:
                data = doc.to_dict() or {}
                migrated, changed = cls.migrate_decision_record(data)
                if changed:
                    store.db.collection("immutable_decision_records").document(doc.id).set(migrated, merge=True)
                    stats["migrated_decisions"] += 1
                    stats["decisions_migrated"] += 1
                else:
                    stats["skipped_already_migrated"] += 1
                    stats["decisions_already_v2"] += 1

        stats["status"] = "COMPLETED"
        stats["completed_at"] = datetime.now(timezone.utc).isoformat()
        return stats
