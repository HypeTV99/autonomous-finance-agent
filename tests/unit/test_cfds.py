import json
import hashlib
import unicodedata
from decimal import Decimal
from compliance_engine import CanonicalFinancialDecisionSerializer, verify_external_auditor_signature, _ED25519_PRIV, ED25519_PUBLIC_KEY_HEX

def test_cfds_golden_vector_reproducibility():
    with open("tests/golden/decision_vectors.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    for vec in data["vectors"]:
        canonical = CanonicalFinancialDecisionSerializer.serialize(vec["payload"])
        assert canonical == vec["canonical_json"]
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        assert digest == vec["sha256"]
        valid, _ = verify_external_auditor_signature(
            canonical_payload_sha256=digest,
            signature_hex=vec["signature"],
            public_key_hex=vec["public_key_hex"],
            signing_key_id=vec["signing_key_id"]
        )
        assert valid is True

def test_cfds_cross_platform_determinism():
    payload_a = {"vendor": "ABC Technologies", "amount": Decimal("100000.00"), "gst": Decimal("18000.00")}
    payload_b = {"gst": Decimal("18000.00"), "amount": Decimal("100000.00"), "vendor": "ABC Technologies"}
    ser_a = CanonicalFinancialDecisionSerializer.serialize(payload_a)
    ser_b = CanonicalFinancialDecisionSerializer.serialize(payload_b)
    assert ser_a == ser_b
    assert hashlib.sha256(ser_a.encode()).hexdigest() == hashlib.sha256(ser_b.encode()).hexdigest()

def test_cfds_fixed_scale_and_mutation_detection():
    payload = {"amount": Decimal("100000.00")}
    mutated = {"amount": Decimal("100000.01")}
    h1 = hashlib.sha256(CanonicalFinancialDecisionSerializer.serialize(payload).encode()).hexdigest()
    h2 = hashlib.sha256(CanonicalFinancialDecisionSerializer.serialize(mutated).encode()).hexdigest()
    assert h1 != h2
