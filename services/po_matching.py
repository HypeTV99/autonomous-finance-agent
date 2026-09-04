from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional, Tuple
from schemas import InvoiceLineItem, LineItemPOMatch


class ThreeWayPOMatchingEngine:
    TOLERANCE_PCT: float = 2.0  # 2% line-item price tolerance ceiling

    # Authorized PO Catalog for Demo / Enterprise Vendor Master
    DEFAULT_PO_REGISTRY: Dict[str, Dict[str, Any]] = {
        "VEND-ALPHA-01": {
            "po_number": "PO-2026-ALPHA-01",
            "authorized_ceiling": Decimal("200000.00"),
            "rates": {
                "DEFAULT": Decimal("1000.00"),
                "IT-CONSULT": Decimal("1000.00"),
                "CLOUD-ARCH": Decimal("1200.00"),
                "DEV-HOURS": Decimal("850.00"),
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
            "authorized_ceiling": Decimal("500000.00"),
            "rates": {
                "DEFAULT": Decimal("500.00"),
                "CONTRACT-LABOR": Decimal("500.00"),
                "SECURITY-OPS": Decimal("450.00")
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
        line_items: List[InvoiceLineItem]
    ) -> Tuple[List[LineItemPOMatch], bool, Decimal]:
        """
        Evaluates extracted invoice lines against authorized PO rates and GRN quantities.
        Returns:
            - matches: List of LineItemPOMatch objects
            - is_fully_compliant: True if all lines are within tolerance
            - total_short_pay_overage: Total variance amount exceeding PO authorized ceiling
        """
        vendor_po = cls.DEFAULT_PO_REGISTRY.get(vendor_id, cls.DEFAULT_PO_REGISTRY["VEND-ALPHA-01"])
        po_rates = vendor_po["rates"]
        po_grn_qtys = vendor_po["grn_verified_quantities"]

        matches: List[LineItemPOMatch] = []
        is_fully_compliant = True
        total_short_pay_overage = Decimal("0.00")

        for item in line_items:
            sku_key = item.sku.upper() if item.sku else "DEFAULT"
            # Find closest rate match or default
            auth_rate = po_rates.get(sku_key, po_rates.get("DEFAULT", Decimal("1000.00")))
            auth_qty = po_grn_qtys.get(sku_key, po_grn_qtys.get("DEFAULT", Decimal("100.00")))

            # Price variance calculation
            if auth_rate > Decimal("0"):
                diff = item.unit_price - auth_rate
                variance_pct = float((diff / auth_rate) * Decimal("100.00"))
            else:
                variance_pct = 0.0

            # Rounding allowance: small rupee drift under ₹10 is ignored
            is_rate_ok = (variance_pct <= cls.TOLERANCE_PCT) or (item.unit_price - auth_rate <= Decimal("10.00"))
            is_qty_ok = item.quantity <= auth_qty

            line_overage = Decimal("0.00")
            if not is_rate_ok:
                is_fully_compliant = False
                rate_diff = max(Decimal("0.00"), item.unit_price - auth_rate)
                line_overage = (rate_diff * item.quantity).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                total_short_pay_overage += line_overage

            matches.append(
                LineItemPOMatch(
                    sku=item.sku or "SKU-GENERIC",
                    description=item.description,
                    billed_quantity=item.quantity,
                    po_authorized_quantity=auth_qty,
                    billed_unit_price=item.unit_price,
                    po_authorized_rate=auth_rate,
                    rate_variance_pct=round(variance_pct, 2),
                    is_within_tolerance=is_rate_ok,
                    is_quantity_compliant=is_qty_ok,
                    short_pay_variance_amount=line_overage
                )
            )

        return matches, is_fully_compliant, total_short_pay_overage

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
