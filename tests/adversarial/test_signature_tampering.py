import hashlib
from decimal import Decimal
from compliance_engine import CanonicalFinancialDecisionSerializer, verify_external_auditor_signature, _ED25519_PRIV, ED25519_PUBLIC_KEY_HEX

def test_signature_tampering_mutations():
    base_payload = {
        "invoice_number": "INV-TAMPER-001",
        "vendor_pan": "AAACA1234T",
        "amount": Decimal("100000.00"),
        "gst": Decimal("18000.00"),
        "tax_rule": "RULE-ITA2025-393-7A"
    }
    canonical_base = CanonicalFinancialDecisionSerializer.serialize(base_payload)
    base_hash = hashlib.sha256(canonical_base.encode()).hexdigest()
    valid_sig = _ED25519_PRIV.sign(base_hash.encode()).hex()

    # Mutation A: Modify Amount (100000.00 -> 100001.00)
    mut_a = dict(base_payload, amount=Decimal("100001.00"))
    hash_a = hashlib.sha256(CanonicalFinancialDecisionSerializer.serialize(mut_a).encode()).hexdigest()
    rep_a = verify_external_auditor_signature(hash_a, valid_sig, ED25519_PUBLIC_KEY_HEX, return_detailed_report=True)
    assert rep_a["overall_verification_status"] == "CRYPTOGRAPHICALLY_INVALID"

    # Mutation B: Modify GST (18000.00 -> 17000.00)
    mut_b = dict(base_payload, gst=Decimal("17000.00"))
    hash_b = hashlib.sha256(CanonicalFinancialDecisionSerializer.serialize(mut_b).encode()).hexdigest()
    rep_b = verify_external_auditor_signature(hash_b, valid_sig, ED25519_PUBLIC_KEY_HEX, return_detailed_report=True)
    assert rep_b["overall_verification_status"] == "CRYPTOGRAPHICALLY_INVALID"

    # Mutation C: Modify Vendor PAN
    mut_c = dict(base_payload, vendor_pan="BBBCB9999K")
    hash_c = hashlib.sha256(CanonicalFinancialDecisionSerializer.serialize(mut_c).encode()).hexdigest()
    rep_c = verify_external_auditor_signature(hash_c, valid_sig, ED25519_PUBLIC_KEY_HEX, return_detailed_report=True)
    assert rep_c["overall_verification_status"] == "CRYPTOGRAPHICALLY_INVALID"

    # Mutation D: Modify Tax Rule (393-7A -> 393-7B)
    mut_d = dict(base_payload, tax_rule="RULE-ITA2025-393-7B")
    hash_d = hashlib.sha256(CanonicalFinancialDecisionSerializer.serialize(mut_d).encode()).hexdigest()
    rep_d = verify_external_auditor_signature(hash_d, valid_sig, ED25519_PUBLIC_KEY_HEX, return_detailed_report=True)
    assert rep_d["overall_verification_status"] == "CRYPTOGRAPHICALLY_INVALID"

    # Mutation E: Signature Substitution (valid signature from payload X on payload Y)
    other_payload = dict(base_payload, invoice_number="INV-OTHER-002")
    other_hash = hashlib.sha256(CanonicalFinancialDecisionSerializer.serialize(other_payload).encode()).hexdigest()
    rep_e = verify_external_auditor_signature(other_hash, valid_sig, ED25519_PUBLIC_KEY_HEX, return_detailed_report=True)
    assert rep_e["overall_verification_status"] == "CRYPTOGRAPHICALLY_INVALID"
