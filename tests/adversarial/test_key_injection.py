from compliance_engine import verify_external_auditor_signature, _ED25519_PRIV, ED25519_PUBLIC_KEY_HEX

def test_key_injection_attacks():
    test_hash = "0eb63bc9dfbcb70232a836573deefb724653444561609446e2ea18fe97586d64"
    valid_sig = _ED25519_PRIV.sign(test_hash.encode()).hex()

    # Attack 1: Rogue Public Key Injection
    rogue_key = "0000000000000000000000000000000000000000000000000000000000000000"
    rep1 = verify_external_auditor_signature(
        canonical_payload_sha256=test_hash, signature_hex=valid_sig, public_key_hex=rogue_key,
        signing_key_id="kms://asia-south1/finance-decision-signer-ed25519-v1", return_detailed_report=True
    )
    assert rep1["overall_verification_status"] == "EMBEDDED_PUBLIC_KEY_TAMPERED"

    # Attack 2: Unknown Key ID Injection
    rep2 = verify_external_auditor_signature(
        canonical_payload_sha256=test_hash, signature_hex=valid_sig,
        signing_key_id="kms://attacker/evil-key", return_detailed_report=True
    )
    assert rep2["overall_verification_status"] == "UNTRUSTED_SIGNING_KEY"
