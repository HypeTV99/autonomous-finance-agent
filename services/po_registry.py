from datetime import datetime, timezone
from decimal import Decimal
import logging
from typing import Any, Dict, List, Optional
from services.po_matching import ThreeWayPOMatchingEngine

logger = logging.getLogger("PoRegistry")


class PoRegistry:
    """
    Purchase Order Registry Service (WS6):
    Maintains active Purchase Orders, authorized line-item rates, versioned amendments,
    and GRN receipts/returns with accepted quantity tracking.
    Integrates directly with ThreeWayPOMatchingEngine.
    """

    _PO_BY_NUMBER: Dict[str, Dict[str, Any]] = {}
    GRN_REGISTRY: Dict[str, Dict[str, Any]] = {}

    @classmethod
    def _init_defaults(cls) -> None:
        """Ensures default PO registry entries are mapped by PO number."""
        for vendor_id, po_data in ThreeWayPOMatchingEngine.DEFAULT_PO_REGISTRY.items():
            po_num = po_data.get("po_number", "").strip().upper()
            if po_num and po_num not in cls._PO_BY_NUMBER:
                if "version" not in po_data:
                    po_data["version"] = 1
                if "authorized_quantities" not in po_data:
                    po_data["authorized_quantities"] = dict(po_data.get("grn_verified_quantities", {}))
                cls._PO_BY_NUMBER[po_num] = po_data

    @classmethod
    def register_purchase_order(
        cls,
        vendor_id: str,
        po_number: str,
        authorized_ceiling: Decimal,
        rates: Dict[str, Decimal],
        grn_quantities: Optional[Dict[str, Decimal]] = None,
        quantities: Optional[Dict[str, Decimal]] = None,
        po_version: int = 1
    ) -> Dict[str, Any]:
        clean_po = po_number.strip().upper()
        auth_qtys = {k.upper(): Decimal(str(v)) for k, v in (quantities or grn_quantities or {}).items()}
        if not auth_qtys:
            auth_qtys = {"DEFAULT": Decimal("100.00")}

        grn_qtys = {k.upper(): Decimal(str(v)) for k, v in (grn_quantities or quantities or {}).items()}
        if not grn_qtys:
            grn_qtys = {"DEFAULT": Decimal("100.00")}

        entry = {
            "po_number": clean_po,
            "vendor_id": vendor_id,
            "authorized_ceiling": Decimal(str(authorized_ceiling)),
            "rates": {k.upper(): Decimal(str(v)) for k, v in rates.items()},
            "authorized_quantities": auth_qtys,
            "grn_verified_quantities": grn_qtys,
            "version": po_version,
            "revisions": []
        }
        ThreeWayPOMatchingEngine.DEFAULT_PO_REGISTRY[vendor_id] = entry
        cls._PO_BY_NUMBER[clean_po] = entry
        logger.info(f"Registered PO '{clean_po}' for vendor '{vendor_id}' v{po_version} ceiling INR {authorized_ceiling}")
        return entry

    @classmethod
    def get_purchase_order(cls, vendor_id: str) -> Optional[Dict[str, Any]]:
        cls._init_defaults()
        return ThreeWayPOMatchingEngine.DEFAULT_PO_REGISTRY.get(vendor_id)

    @classmethod
    def get_purchase_order_by_number(cls, po_number: str) -> Optional[Dict[str, Any]]:
        cls._init_defaults()
        clean_po = po_number.strip().upper()
        entry = cls._PO_BY_NUMBER.get(clean_po)
        if entry:
            return entry
        for p in ThreeWayPOMatchingEngine.DEFAULT_PO_REGISTRY.values():
            if p.get("po_number", "").strip().upper() == clean_po:
                return p
        return None

    @classmethod
    def list_purchase_orders(cls) -> Dict[str, Dict[str, Any]]:
        cls._init_defaults()
        return ThreeWayPOMatchingEngine.DEFAULT_PO_REGISTRY

    @classmethod
    def amend_purchase_order(
        cls,
        po_number: str,
        new_rates: Optional[Dict[str, Decimal]] = None,
        new_quantities: Optional[Dict[str, Decimal]] = None,
        new_ceiling: Optional[Decimal] = None,
        reason: str = ""
    ) -> Dict[str, Any]:
        """
        Creates a versioned amendment to an existing Purchase Order.
        Preserves historical revision snapshots while incrementing active version.
        """
        cls._init_defaults()
        clean_po = po_number.strip().upper()
        entry = cls.get_purchase_order_by_number(clean_po)
        if not entry:
            raise ValueError(f"Purchase order '{po_number}' not found for amendment")

        now_iso = datetime.now(timezone.utc).isoformat()
        revision_snapshot = {
            "version": entry.get("version", 1),
            "rates": dict(entry.get("rates", {})),
            "authorized_quantities": dict(entry.get("authorized_quantities", {})),
            "authorized_ceiling": entry.get("authorized_ceiling", Decimal("0.00")),
            "amended_at": now_iso,
            "reason": reason
        }
        entry.setdefault("revisions", []).append(revision_snapshot)

        entry["version"] = entry.get("version", 1) + 1

        if new_rates is not None:
            entry["rates"].update({k.upper(): Decimal(str(v)) for k, v in new_rates.items()})

        if new_quantities is not None:
            entry["authorized_quantities"].update({k.upper(): Decimal(str(v)) for k, v in new_quantities.items()})
            entry["grn_verified_quantities"].update({k.upper(): Decimal(str(v)) for k, v in new_quantities.items()})

        if new_ceiling is not None:
            entry["authorized_ceiling"] = Decimal(str(new_ceiling))

        logger.info(f"Amended PO '{clean_po}' to v{entry['version']}. Reason: '{reason}'")
        return entry

    @classmethod
    def record_grn_receipt(
        cls,
        grn_number: str,
        po_number: str,
        vendor_id: str,
        received_quantities: Dict[str, Decimal],
        rejected_quantities: Optional[Dict[str, Decimal]] = None,
        returned_quantities: Optional[Dict[str, Decimal]] = None,
        grn_version: int = 1
    ) -> Dict[str, Any]:
        """
        Records a Goods Received Note (GRN) with accepted quantity calculation:
        accepted_quantity = received - rejected - returned
        """
        clean_grn = grn_number.strip().upper()
        clean_po = po_number.strip().upper()

        rec_map = {k.upper(): Decimal(str(v)) for k, v in received_quantities.items()}
        rej_map = {k.upper(): Decimal(str(v)) for k, v in (rejected_quantities or {}).items()}
        ret_map = {k.upper(): Decimal(str(v)) for k, v in (returned_quantities or {}).items()}

        accepted: Dict[str, Decimal] = {}
        for sku, rec_qty in rec_map.items():
            rej = rej_map.get(sku, Decimal("0.00"))
            ret = ret_map.get(sku, Decimal("0.00"))
            accepted[sku] = max(Decimal("0.00"), rec_qty - rej - ret)

        now_iso = datetime.now(timezone.utc).isoformat()
        grn_entry = {
            "grn_number": clean_grn,
            "po_number": clean_po,
            "vendor_id": vendor_id,
            "received_quantities": rec_map,
            "rejected_quantities": rej_map,
            "returned_quantities": ret_map,
            "accepted_quantities": accepted,
            "version": grn_version,
            "created_at": now_iso,
            "revisions": []
        }
        cls.GRN_REGISTRY[clean_grn] = grn_entry
        logger.info(f"Recorded GRN '{clean_grn}' for PO '{clean_po}' accepted={accepted}")
        return grn_entry

    @classmethod
    def adjust_grn_returns(
        cls,
        grn_number: str,
        return_quantities: Dict[str, Decimal],
        reason: str = ""
    ) -> Dict[str, Any]:
        """
        Adjusts GRN for subsequently returned goods, reducing accepted capacity.
        """
        clean_grn = grn_number.strip().upper()
        entry = cls.GRN_REGISTRY.get(clean_grn)
        if not entry:
            raise ValueError(f"GRN '{grn_number}' not found for return adjustment")

        now_iso = datetime.now(timezone.utc).isoformat()
        entry.setdefault("revisions", []).append({
            "version": entry.get("version", 1),
            "accepted_quantities": dict(entry.get("accepted_quantities", {})),
            "returned_quantities": dict(entry.get("returned_quantities", {})),
            "adjusted_at": now_iso,
            "reason": reason
        })

        entry["version"] = entry.get("version", 1) + 1

        for sku_raw, ret_qty in return_quantities.items():
            sku = sku_raw.strip().upper()
            prior_ret = entry["returned_quantities"].get(sku, Decimal("0.00"))
            entry["returned_quantities"][sku] = prior_ret + Decimal(str(ret_qty))

            rec = entry["received_quantities"].get(sku, Decimal("0.00"))
            rej = entry["rejected_quantities"].get(sku, Decimal("0.00"))
            tot_ret = entry["returned_quantities"][sku]
            entry["accepted_quantities"][sku] = max(Decimal("0.00"), rec - rej - tot_ret)

        logger.info(f"Adjusted returns on GRN '{clean_grn}' to v{entry['version']}. New accepted: {entry['accepted_quantities']}")
        return entry

    @classmethod
    def get_grn(cls, grn_number: str) -> Optional[Dict[str, Any]]:
        return cls.GRN_REGISTRY.get(grn_number.strip().upper())

    @classmethod
    def list_grns(cls) -> Dict[str, Dict[str, Any]]:
        return cls.GRN_REGISTRY

    @classmethod
    def reset(cls) -> None:
        """Resets registry state (for test isolation)."""
        cls._PO_BY_NUMBER.clear()
        cls.GRN_REGISTRY.clear()
        cls._init_defaults()

