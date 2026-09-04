from decimal import Decimal
import logging
from typing import Any, Dict, List, Optional
from services.po_matching import ThreeWayPOMatchingEngine

logger = logging.getLogger("PoRegistry")


class PoRegistry:
    """
    Purchase Order Registry Service (WS6):
    Maintains active Purchase Orders, authorized line-item rates, and GRN receipts.
    Integrates directly with ThreeWayPOMatchingEngine.
    """

    @classmethod
    def register_purchase_order(
        cls,
        vendor_id: str,
        po_number: str,
        authorized_ceiling: Decimal,
        rates: Dict[str, Decimal],
        grn_quantities: Optional[Dict[str, Decimal]] = None
    ) -> Dict[str, Any]:
        entry = {
            "po_number": po_number,
            "authorized_ceiling": Decimal(str(authorized_ceiling)),
            "rates": {k: Decimal(str(v)) for k, v in rates.items()},
            "grn_verified_quantities": {k: Decimal(str(v)) for k, v in (grn_quantities or {}).items()}
        }
        ThreeWayPOMatchingEngine.DEFAULT_PO_REGISTRY[vendor_id] = entry
        logger.info(f"Registered PO '{po_number}' for vendor '{vendor_id}' with ceiling INR {authorized_ceiling}")
        return entry

    @classmethod
    def get_purchase_order(cls, vendor_id: str) -> Optional[Dict[str, Any]]:
        return ThreeWayPOMatchingEngine.DEFAULT_PO_REGISTRY.get(vendor_id)

    @classmethod
    def list_purchase_orders(cls) -> Dict[str, Dict[str, Any]]:
        return ThreeWayPOMatchingEngine.DEFAULT_PO_REGISTRY
