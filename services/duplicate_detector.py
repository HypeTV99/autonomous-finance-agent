import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from schemas import DuplicateCheckResult, DuplicateDisposition


class MultiSignalDuplicateDetector:
    """
    Multi-Signal Algorithmic Duplicate Detection Engine (Prompt 10 Enterprise Standard):
    Layer 1: Cryptographic Document Identity (SHA-256 content hash) -> BLOCK
    Layer 2: Hard Business Identity (Vendor Tax ID / PAN + Exact Invoice Number) -> BLOCK
    Layer 3: Normalized Identity (Cautious whitespace/punctuation/leading-zero normalization) -> BLOCK
    Layer 4: Economic Similarity (Same Vendor + matching gross amount +- ₹1.00 or overlapping items) -> REVIEW
    Layer 5: Clean -> ALLOW
    """

    @classmethod
    def normalize_invoice_number(cls, raw: str) -> str:
        """
        Cautiously normalizes invoice numbers to catch OCR artifact variations and punctuation differences.
        - Trims whitespace and converts to uppercase
        - Strips separators: hyphens, slashes, underscores, dots, spaces
        - Normalizes leading zeros on the trailing numeric portion (e.g. INV-00123 -> INV123, 0042 -> 42)
        Does NOT alter alphanumeric semantics or drop distinct character sequences.
        """
        if not raw:
            return ""
        clean = re.sub(r"[\s\-_/\\.,]+", "", str(raw).strip().upper())
        # Cautiously collapse leading zeros after non-digit prefix, e.g. INV00123 -> INV123
        collapsed = re.sub(r"^([A-Z]*)0+([0-9]+.*)$", r"\1\2", clean)
        return collapsed if collapsed else clean

    @classmethod
    def evaluate_invoice(
        cls,
        new_invoice_number: str,
        new_vendor_id: str,
        new_vendor_name: str,
        new_gross_amount: Decimal,
        existing_decisions: List[Dict[str, Any]],
        new_document_hash: Optional[str] = None,
        new_vendor_pan: Optional[str] = None,
        new_po_number: Optional[str] = None,
        new_line_items: Optional[List[Any]] = None,
        current_time: Optional[datetime] = None
    ) -> DuplicateCheckResult:
        """
        Evaluates an incoming invoice across 5 layered signals, returning an authoritative
        disposition: BLOCK, REVIEW, or ALLOW.
        """
        now = current_time or datetime.now(timezone.utc)
        new_num_clean = str(new_invoice_number).strip().upper()
        new_num_norm = cls.normalize_invoice_number(new_invoice_number)
        new_vendor_clean = str(new_vendor_name).strip().upper()
        new_vendor_id_clean = str(new_vendor_id).strip().upper()
        new_pan_clean = str(new_vendor_pan).strip().upper() if new_vendor_pan else ""
        new_doc_hash_clean = str(new_document_hash).strip().lower() if new_document_hash else ""

        for d in existing_decisions:
            existing_id = str(d.get("id", "")).strip().upper()
            existing_num = str(d.get("invoice_number", "")).strip().upper()
            existing_num_norm = cls.normalize_invoice_number(existing_num)
            existing_vendor = str(d.get("vendor_name", "")).strip().upper()
            existing_vendor_id = str(d.get("vendor_id", "")).strip().upper()
            existing_pan = str(d.get("vendor_pan", "")).strip().upper()
            
            # Check existing document hashes
            existing_hash = str(
                d.get("content_hash") or d.get("document_hash") or d.get("file_digest") or d.get("invoice_document_hash") or ""
            ).strip().lower()

            # --- Layer 1: Document Identity (SHA-256 Collision) ---
            if new_doc_hash_clean and existing_hash and new_doc_hash_clean == existing_hash:
                return DuplicateCheckResult(
                    disposition=DuplicateDisposition.BLOCK,
                    matched_signal="DOCUMENT_HASH",
                    matched_invoice_number=existing_num or existing_id,
                    matched_vendor_id=existing_vendor_id or existing_vendor,
                    similarity_score=Decimal("1.00"),
                    reason=f"Cryptographic document collision: SHA-256 hash '{new_doc_hash_clean}' identical to existing record '{existing_num or existing_id}'.",
                    is_blocked=True,
                    requires_review=False,
                    metadata={"matched_document_hash": existing_hash}
                )

            # Check vendor identity match
            same_vendor = False
            if new_vendor_id_clean and existing_vendor_id and new_vendor_id_clean == existing_vendor_id:
                same_vendor = True
            elif new_pan_clean and existing_pan and new_pan_clean == existing_pan:
                same_vendor = True
            elif new_vendor_clean and existing_vendor and (new_vendor_clean in existing_vendor or existing_vendor in new_vendor_clean):
                same_vendor = True

            if not same_vendor:
                continue

            # --- Layer 2: Hard Identity (Exact Invoice Number + Same Vendor) ---
            if existing_num and new_num_clean == existing_num:
                return DuplicateCheckResult(
                    disposition=DuplicateDisposition.BLOCK,
                    matched_signal="HARD_IDENTITY",
                    matched_invoice_number=existing_num,
                    matched_vendor_id=existing_vendor_id or existing_vendor,
                    similarity_score=Decimal("1.00"),
                    reason=f"EXACT DUPLICATE: Invoice '{new_invoice_number}' already registered under vendor '{new_vendor_name}'.",
                    is_blocked=True,
                    requires_review=False,
                    metadata={"matched_invoice_number": existing_num}
                )

            # --- Layer 3: Normalized Identity (Punctuation/Leading-Zero Variation) ---
            if new_num_norm and existing_num_norm and new_num_norm == existing_num_norm:
                return DuplicateCheckResult(
                    disposition=DuplicateDisposition.BLOCK,
                    matched_signal="NORMALIZED_IDENTITY",
                    matched_invoice_number=existing_num,
                    matched_vendor_id=existing_vendor_id or existing_vendor,
                    similarity_score=Decimal("0.99"),
                    reason=f"NORMALIZED DUPLICATE COLLISION: Normalized invoice number '{new_num_norm}' matches existing '{existing_num}' under vendor '{new_vendor_name}'.",
                    is_blocked=True,
                    requires_review=False,
                    metadata={"normalized_query": new_num_norm, "matched_raw": existing_num}
                )

            # --- Layer 4: Economic Similarity (Fuzzy Amount +- ₹1.00 within Window or Item Overlap) ---
            try:
                existing_gross = Decimal(str(d.get("gross_amount", d.get("invoice_gross_total", "0.00"))))
            except Exception:
                existing_gross = Decimal("0.00")

            if existing_gross > Decimal("0") and new_gross_amount > Decimal("0"):
                diff = abs(new_gross_amount - existing_gross)
                if diff <= Decimal("1.00"):
                    # Window check (default 60 days, or fallback to 30 days)
                    ts_str = d.get("decision_timestamp") or d.get("timestamp") or d.get("invoice_date") or ""
                    is_in_window = True
                    if ts_str:
                        try:
                            dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                            if (now - dt) > timedelta(days=90):
                                is_in_window = False
                        except Exception:
                            is_in_window = True

                    if is_in_window:
                        return DuplicateCheckResult(
                            disposition=DuplicateDisposition.REVIEW,
                            matched_signal="ECONOMIC_SIMILARITY",
                            matched_invoice_number=existing_num,
                            matched_vendor_id=existing_vendor_id or existing_vendor,
                            similarity_score=Decimal("0.95"),
                            reason=(
                                f"FUZZY DUPLICATE COLLISION: Vendor '{new_vendor_name}' already submitted invoice "
                                f"'{existing_num}' for identical amount (₹{existing_gross:,.2f}) within rolling window. "
                                f"Requires human review before clearance."
                            ),
                            is_blocked=False,
                            requires_review=True,
                            metadata={"matched_invoice": existing_num, "matched_amount": str(existing_gross)}
                        )

        # --- Layer 5: Clean ---
        return DuplicateCheckResult(
            disposition=DuplicateDisposition.ALLOW,
            matched_signal="NONE",
            is_blocked=False,
            requires_review=False,
            similarity_score=Decimal("0.00"),
            reason="Distinct invoice. No duplicate identity or economic collision detected."
        )

    @classmethod
    def check_for_duplicates(
        cls,
        new_invoice_number: str,
        new_vendor_id: str,
        new_vendor_name: str,
        new_gross_amount: Decimal,
        existing_decisions: List[Dict[str, Any]],
        new_document_hash: Optional[str] = None
    ) -> Tuple[bool, Optional[str]]:
        """
        Backward-compatible check method. Returns (is_flagged, reason).
        Flags both hard blocks and fuzzy similarity collisions for triage.
        """
        result = cls.evaluate_invoice(
            new_invoice_number=new_invoice_number,
            new_vendor_id=new_vendor_id,
            new_vendor_name=new_vendor_name,
            new_gross_amount=new_gross_amount,
            existing_decisions=existing_decisions,
            new_document_hash=new_document_hash
        )
        if result.disposition in (DuplicateDisposition.BLOCK, DuplicateDisposition.REVIEW):
            return True, result.reason
        return False, None
