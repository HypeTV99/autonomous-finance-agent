from compliance_engine import verify_external_auditor_signature, _ED25519_PRIV, ED25519_PUBLIC_KEY_HEX

def test_registry_tampering_mismatch():
    test_hash = "0eb63bc9dfbcb70232a836573deefb724653444561609446e2ea18fe97586d64"
    valid_sig = _ED25519_PRIV.sign(test_hash.encode()).hex()

    # If payload claims a different public key than the Root Registry anchor
    fake_pub = "1111111111111111111111111111111111111111111111111111111111111111"
    rep = verify_external_auditor_signature(
        canonical_payload_sha256=test_hash, signature_hex=valid_sig, public_key_hex=fake_pub,
        signing_key_id="kms://asia-south1/finance-decision-signer-ed25519-v1", return_detailed_report=True
    )
    assert rep["overall_verification_status"] == "EMBEDDED_PUBLIC_KEY_TAMPERED"
