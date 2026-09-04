from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple


class MultiSignalDuplicateDetector:
    """
    Multi-Signal Algorithmic Duplicate Detection Engine (Ramp/Coupa Standard):
    1. Signal 1 (Exact Match): Same Vendor + Exact Invoice Number collision.
    2. Signal 2 (Fuzzy Window Match): Same Vendor + Identical Gross Amount (+- Re 1.00) within 30-day window.
    """

    @classmethod
    def check_for_duplicates(
        cls,
        new_invoice_number: str,
        new_vendor_id: str,
        new_vendor_name: str,
        new_gross_amount: Decimal,
        existing_decisions: List[Dict[str, Any]]
    ) -> Tuple[bool, Optional[str]]:
        new_num_clean = new_invoice_number.strip().upper()
        new_vendor_clean = new_vendor_name.strip().upper()

        for d in existing_decisions:
            existing_num = str(d.get("invoice_number", "")).strip().upper()
            existing_vendor = str(d.get("vendor_name", "")).strip().upper()
            existing_vendor_id = str(d.get("vendor_id", "")).strip().upper()
            
            # Don't match self if re-evaluating
            if d.get("id") == new_invoice_number or existing_num == new_num_clean:
                # Exact invoice number collision under same vendor
                if existing_vendor_id == new_vendor_id.upper() or existing_vendor == new_vendor_clean:
                    return True, f"EXACT DUPLICATE: Invoice '{new_invoice_number}' already registered under vendor '{new_vendor_name}'"

            # Check 2: Fuzzy amount & window collision under same vendor
            same_vendor = (existing_vendor_id == new_vendor_id.upper()) or (existing_vendor == new_vendor_clean)
            if same_vendor:
                try:
                    existing_gross = Decimal(str(d.get("gross_amount", d.get("invoice_gross_total", "0.00"))))
                except Exception:
                    existing_gross = Decimal("0.00")

                if existing_gross > Decimal("0"):
                    diff = abs(new_gross_amount - existing_gross)
                    if diff <= Decimal("1.00"):
                        # Check timestamp within 30 days
                        ts_str = d.get("decision_timestamp") or d.get("timestamp") or ""
                        if ts_str:
                            try:
                                dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                                if (datetime.now(timezone.utc) - dt) < timedelta(days=30):
                                    return True, (
                                        f"FUZZY DUPLICATE COLLISION: Vendor '{new_vendor_name}' already submitted invoice "
                                        f"'{existing_num}' for identical amount (₹{existing_gross:,.2f}) within last 30 days."
                                    )
                            except Exception:
                                pass

        return False, None
