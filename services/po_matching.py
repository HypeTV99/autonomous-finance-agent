from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional, Tuple
from schemas import InvoiceLineItem, LineItemPOMatch


class ThreeWayPOMatchingEngine:
    TOLERANCE_PCT: float = 2.0  # 2% line-item price tolerance ceiling
    PETTY_ROUNDING_RUPEE_CAP: Decimal = Decimal("10.00")  # Max rupee drift for petty rounding
    PETTY_ROUNDING_PCT_CAP: float = 5.0  # Max percentage cap for petty rounding to prevent leakage

    _in_memory_po_allocations: Dict[str, Dict[str, Decimal]] = {}
    _in_memory_grn_allocations: Dict[str, Dict[str, Decimal]] = {}

    # Authorized PO Catalog for Demo / Enterprise Vendor Master
    DEFAULT_PO_REGISTRY: Dict[str, Dict[str, Any]] = {
        "VEND-ALPHA-01": {
            "po_number": "PO-2026-ALPHA-01",
            "version": 1,
            "authorized_ceiling": Decimal("200000.00"),
            "rates": {
                "DEFAULT": Decimal("1000.00"),
                "IT-CONSULT": Decimal("1000.00"),
                "CLOUD-ARCH": Decimal("1200.00"),
                "DEV-HOURS": Decimal("850.00"),
            },
            "authorized_quantities": {
                "DEFAULT": Decimal("100.00"),
                "IT-CONSULT": Decimal("100.00"),
                "CLOUD-ARCH": Decimal("50.00"),
                "DEV-HOURS": Decimal("200.00"),
            },
            "grn_verified_quantities": {
                "DEFAULT": Decimal("100.00"),
                "IT-CONSULT": Decimal("100.00"),
                "CLOUD-ARCH": Decimal("50.00"),
                "DEV-HOURS": Decimal("200.00"),
            }
        },
        "VEND-BETA-02": {
            "po_number": "PO-2026-BETA-02",
            "version": 1,
            "authorized_ceiling": Decimal("500000.00"),
            "rates": {
                "DEFAULT": Decimal("500.00"),
                "CONTRACT-LABOR": Decimal("500.00"),
                "SECURITY-OPS": Decimal("450.00")
            },
            "authorized_quantities": {
                "DEFAULT": Decimal("500.00"),
                "CONTRACT-LABOR": Decimal("500.00"),
                "SECURITY-OPS": Decimal("300.00")
            },
            "grn_verified_quantities": {
                "DEFAULT": Decimal("500.00"),
                "CONTRACT-LABOR": Decimal("500.00"),
                "SECURITY-OPS": Decimal("300.00")
            }
        }
    }

    @classmethod
    def evaluate_line_items(
        cls,
        vendor_id: str,
        line_items: List[InvoiceLineItem],
        po_number: Optional[str] = None,
        store: Optional[Any] = None,
        invoice_number: Optional[str] = None,
        grn_number: Optional[str] = None,
        po_version: Optional[int] = None,
        grn_version: Optional[int] = None,
        auto_allocate: bool = False
    ) -> Tuple[List[LineItemPOMatch], bool, Decimal]:
        """
        Evaluates extracted invoice lines against authorized PO rates and cumulative PO/GRN quantities.
        Returns:
            - matches: List of LineItemPOMatch objects
            - is_fully_compliant: True if all lines are within rate tolerance and cumulative quantities
            - total_short_pay_overage: Total variance amount exceeding PO authorized ceiling
        """
        from services.po_registry import PoRegistry
        clean_vendor = vendor_id.strip().upper() if vendor_id else "VEND-ALPHA-01"
        clean_po = po_number.strip().upper() if po_number else None
        clean_grn = grn_number.strip().upper() if grn_number else None

        # 1. Resolve PO
        vendor_po = None
        if clean_po:
            vendor_po = PoRegistry.get_purchase_order_by_number(clean_po)
        if not vendor_po:
            vendor_po = PoRegistry.get_purchase_order(clean_vendor) or cls.DEFAULT_PO_REGISTRY.get(clean_vendor)
        if not vendor_po:
            vendor_po = cls.DEFAULT_PO_REGISTRY["VEND-ALPHA-01"]

        effective_po_number = clean_po or vendor_po.get("po_number", "PO-2026-ALPHA-01")
        effective_po_version = po_version or vendor_po.get("version", 1)

        po_rates = vendor_po.get("rates", {})
        po_auth_qtys = vendor_po.get("authorized_quantities") or vendor_po.get("grn_verified_quantities", {})

        # 2. Resolve GRN
        grn_entry = None
        if clean_grn:
            grn_entry = PoRegistry.get_grn(clean_grn)

        if grn_entry:
            grn_accepted_qtys = grn_entry.get("accepted_quantities", {})
        else:
            grn_accepted_qtys = vendor_po.get("grn_verified_quantities", {})

        # 3. Retrieve prior cumulative allocations
        if store is not None:
            prior_po = store.get_cumulative_po_allocations(effective_po_number)
            prior_grn = store.get_cumulative_grn_allocations(clean_grn) if clean_grn else {}
        else:
            prior_po = cls._in_memory_po_allocations.get(effective_po_number.strip().upper(), {})
            prior_grn = cls._in_memory_grn_allocations.get(clean_grn, {}) if clean_grn else {}

        matches: List[LineItemPOMatch] = []
        is_fully_compliant = True
        total_short_pay_overage = Decimal("0.00")

        # Intra-invoice running allocation tracking for duplicate SKUs
        running_invoice_po: Dict[str, Decimal] = {}
        running_invoice_grn: Dict[str, Decimal] = {}

        for item in line_items:
            sku_key = item.sku.upper() if item.sku else "DEFAULT"
            auth_rate = po_rates.get(sku_key, po_rates.get("DEFAULT", Decimal("1000.00")))
            auth_po_qty = po_auth_qtys.get(sku_key, po_auth_qtys.get("DEFAULT", Decimal("100.00")))
            auth_grn_qty = grn_accepted_qtys.get(sku_key, grn_accepted_qtys.get("DEFAULT", auth_po_qty)) if grn_accepted_qtys else auth_po_qty

            # Rate check
            if auth_rate > Decimal("0"):
                diff = item.unit_price - auth_rate
                variance_pct = float((diff / auth_rate) * Decimal("100.00"))
            else:
                diff = Decimal("0.00")
                variance_pct = 0.0

            if diff <= Decimal("0.00"):
                is_rate_ok = True
            else:
                is_rate_ok = (variance_pct <= cls.TOLERANCE_PCT) or (
                    diff <= cls.PETTY_ROUNDING_RUPEE_CAP and variance_pct <= cls.PETTY_ROUNDING_PCT_CAP
                )

            # Cumulative quantity check
            prev_po = prior_po.get(sku_key, Decimal("0.00")) + running_invoice_po.get(sku_key, Decimal("0.00"))
            cum_po_qty = prev_po + item.quantity
            is_po_qty_ok = (cum_po_qty <= auth_po_qty)
            running_invoice_po[sku_key] = running_invoice_po.get(sku_key, Decimal("0.00")) + item.quantity

            prev_grn = prior_grn.get(sku_key, Decimal("0.00")) + running_invoice_grn.get(sku_key, Decimal("0.00"))
            cum_grn_qty = prev_grn + item.quantity
            is_grn_qty_ok = (cum_grn_qty <= auth_grn_qty) if auth_grn_qty is not None else True
            running_invoice_grn[sku_key] = running_invoice_grn.get(sku_key, Decimal("0.00")) + item.quantity

            is_qty_ok = is_po_qty_ok and is_grn_qty_ok

            line_overage = Decimal("0.00")
            if not is_rate_ok:
                rate_diff = max(Decimal("0.00"), diff)
                line_overage = (rate_diff * item.quantity).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                total_short_pay_overage += line_overage

            if not (is_rate_ok and is_qty_ok):
                is_fully_compliant = False

            matches.append(
                LineItemPOMatch(
                    sku=item.sku or "SKU-GENERIC",
                    description=item.description,
                    billed_quantity=item.quantity,
                    po_authorized_quantity=auth_po_qty,
                    billed_unit_price=item.unit_price,
                    po_authorized_rate=auth_rate,
                    rate_variance_pct=round(variance_pct, 2),
                    is_within_tolerance=is_rate_ok,
                    is_quantity_compliant=is_qty_ok,
                    short_pay_variance_amount=line_overage,
                    cumulative_allocated_quantity=cum_po_qty,
                    grn_authorized_quantity=auth_grn_qty,
                    cumulative_grn_allocated=cum_grn_qty,
                    is_po_quantity_compliant=is_po_qty_ok,
                    is_grn_quantity_compliant=is_grn_qty_ok
                )
            )

        # Auto-allocate if requested, compliant, and invoice_number provided
        if auto_allocate and is_fully_compliant and invoice_number:
            if store:
                req_items = [
                    {
                        "sku": (it.sku or "DEFAULT").strip().upper(),
                        "quantity": it.quantity,
                        "unit_price": it.unit_price
                    }
                    for it in line_items
                ]
                alloc_ok, record, msg = store.atomic_allocate_procurement(
                    invoice_number=invoice_number,
                    po_number=effective_po_number,
                    po_version=effective_po_version,
                    vendor_id=clean_vendor,
                    requested_items=req_items,
                    po_limits=po_auth_qtys,
                    grn_number=clean_grn,
                    grn_version=grn_version or (grn_entry.get("version", 1) if grn_entry else 1),
                    grn_limits=grn_accepted_qtys if clean_grn else None
                )
                if not alloc_ok:
                    is_fully_compliant = False
            else:
                po_key = effective_po_number.strip().upper()
                in_mem_po = cls._in_memory_po_allocations.setdefault(po_key, {})
                for sku, q in running_invoice_po.items():
                    in_mem_po[sku] = in_mem_po.get(sku, Decimal("0.00")) + q
                if clean_grn:
                    in_mem_grn = cls._in_memory_grn_allocations.setdefault(clean_grn, {})
                    for sku, q in running_invoice_grn.items():
                        in_mem_grn[sku] = in_mem_grn.get(sku, Decimal("0.00")) + q

        return matches, is_fully_compliant, total_short_pay_overage

    @classmethod
    def allocate_procurement(
        cls,
        store: Any,
        invoice_number: str,
        vendor_id: str,
        line_items: List[InvoiceLineItem],
        po_number: Optional[str] = None,
        po_version: int = 1,
        grn_number: Optional[str] = None,
        grn_version: int = 1
    ) -> Tuple[bool, Optional[Dict[str, Any]], str]:
        """Directly commits an atomic procurement allocation in the store."""
        from services.po_registry import PoRegistry
        clean_vendor = vendor_id.strip().upper() if vendor_id else "VEND-ALPHA-01"
        clean_po = po_number.strip().upper() if po_number else None
        clean_grn = grn_number.strip().upper() if grn_number else None

        vendor_po = None
        if clean_po:
            vendor_po = PoRegistry.get_purchase_order_by_number(clean_po)
        if not vendor_po:
            vendor_po = PoRegistry.get_purchase_order(clean_vendor) or cls.DEFAULT_PO_REGISTRY.get(clean_vendor)
        if not vendor_po:
            vendor_po = cls.DEFAULT_PO_REGISTRY["VEND-ALPHA-01"]

        effective_po_num = clean_po or vendor_po.get("po_number", "PO-2026-ALPHA-01")
        effective_po_ver = po_version or vendor_po.get("version", 1)
        po_limits = vendor_po.get("authorized_quantities") or vendor_po.get("grn_verified_quantities", {})

        grn_limits = None
        effective_grn_ver = grn_version
        if clean_grn:
            grn_entry = PoRegistry.get_grn(clean_grn)
            if grn_entry:
                grn_limits = grn_entry.get("accepted_quantities")
                effective_grn_ver = grn_version or grn_entry.get("version", 1)
            else:
                grn_limits = vendor_po.get("grn_verified_quantities")

        requested_items = [
            {
                "sku": (it.sku or "DEFAULT").strip().upper(),
                "quantity": it.quantity,
                "unit_price": it.unit_price
            }
            for it in line_items
        ]

        return store.atomic_allocate_procurement(
            invoice_number=invoice_number,
            po_number=effective_po_num,
            po_version=effective_po_ver,
            vendor_id=clean_vendor,
            requested_items=requested_items,
            po_limits=po_limits,
            grn_number=clean_grn,
            grn_version=effective_grn_ver,
            grn_limits=grn_limits
        )

    @classmethod
    def release_procurement_allocation(
        cls,
        store: Any,
        invoice_number: str,
        po_number: Optional[str] = None
    ) -> bool:
        """Releases active allocations for an invoice upon cancellation/rejection."""
        if store:
            return store.release_procurement_allocation(invoice_number, po_number)
        return False

    @classmethod
    def reset(cls) -> None:
        """Resets in-memory allocations."""
        cls._in_memory_po_allocations.clear()
        cls._in_memory_grn_allocations.clear()

    @classmethod
    def generate_short_pay_debit_note(
        cls,
        invoice_number: str,
        vendor_id: str,
        overage_amount: Decimal,
        override_reason: str = "Short-Pay to authorized PO rate ceiling"
    ) -> Dict[str, Any]:
        """Provisions a formal customer debit note to offset overbilled invoice variance."""
        from datetime import datetime, timezone
        dn_id = f"DN-{invoice_number.replace('INV-', '')}-POVAR"
        return {
            "debit_note_id": dn_id,
            "invoice_reference": invoice_number,
            "vendor_id": vendor_id,
            "debit_amount": str(overage_amount),
            "reason": override_reason,
            "issued_at": datetime.now(timezone.utc).isoformat(),
            "accounting_entry": {
                "debit_account": "2010 - Accounts Payable (Vendor Offset)",
                "credit_account": "6090 - Price Variance Recovery / Contra Expense",
                "amount": str(overage_amount)
            }
        }
