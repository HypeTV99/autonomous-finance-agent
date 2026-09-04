from compliance_engine import verify_external_auditor_signature, EnterpriseKeyRegistry, _ED25519_PRIV, ED25519_PUBLIC_KEY_HEX
from schemas import CompromiseAdjudicationCertificate, KeyCompromiseOutcome, AdjudicatingAuthoritySignature

def test_compromise_boundary_matrix():
    test_hash = "0eb63bc9dfbcb70232a836573deefb724653444561609446e2ea18fe97586d64"
    sig_hex = _ED25519_PRIV.sign(test_hash.encode()).hex()
    target_key = "kms://asia-south1/boundary-key-2026"

    EnterpriseKeyRegistry.register_key({
        "key_id": target_key, "algorithm": "Ed25519", "public_key_hex": ED25519_PUBLIC_KEY_HEX,
        "status": "COMPROMISED", "valid_from": "2026-01-01T00:00:00Z", "valid_until": "2026-12-31T23:59:59Z",
        "root_authority": "FinanceAgent-Enterprise-Trust-Anchor-v1"
    })

    ciso_sig = AdjudicatingAuthoritySignature(
        role="CISO", identity="ciso@ent.com", public_key_hex=ED25519_PUBLIC_KEY_HEX, signature_hex="sig1", signed_at="2026-08-23T22:00:00Z"
    )
    cert = CompromiseAdjudicationCertificate(
        adjudication_id="ADJUD-BOUNDARY-01", key_id=target_key, outcome=KeyCompromiseOutcome.COMPROMISE_CONFIRMED,
        incident_reference="INC-BOUNDARY", compromise_detection_timestamp="2026-08-20T00:00:00Z",
        decision_effective_timestamp="2026-08-23T22:00:00Z",
        compromise_window_start="2026-08-20T00:00:00Z", compromise_window_end="2026-08-22T00:00:00Z",
        evidence_manifest_hash="ev_hash", previous_key_registry_state_hash="prev_hash", new_key_registry_state_hash="new_hash",
        adjudicating_authorities=[ciso_sig], remediated_with_key_id="kms://asia-south1/remediated-v2", audit_notes="Boundary test",
        certificate_canonical_hash="cert_hash", certificate_signature="cert_sig", adjudicated_at="2026-08-23T22:00:00Z"
    )
    EnterpriseKeyRegistry.adjudicate_compromise(target_key, cert)

    # 1. Boundary: t < start (2026-08-19 23:59:59) -> ADMISSIBLE
    r1 = verify_external_auditor_signature(test_hash, sig_hex, signing_key_id=target_key, signed_at="2026-08-19T23:59:59Z", return_detailed_report=True)
    assert r1["overall_verification_status"] == "CRYPTOGRAPHICALLY_VALID_AND_ADMISSIBLE"

    # 2. Boundary: t = start (2026-08-20 00:00:00) -> INVALIDATED
    r2 = verify_external_auditor_signature(test_hash, sig_hex, signing_key_id=target_key, signed_at="2026-08-20T00:00:00Z", return_detailed_report=True)
    assert r2["overall_verification_status"] == "CRYPTOGRAPHICALLY_VALID_BUT_FINANCIALLY_INVALIDATED"

    # 3. Boundary: t inside (2026-08-21 12:00:00) -> INVALIDATED
    r3 = verify_external_auditor_signature(test_hash, sig_hex, signing_key_id=target_key, signed_at="2026-08-21T12:00:00Z", return_detailed_report=True)
    assert r3["overall_verification_status"] == "CRYPTOGRAPHICALLY_VALID_BUT_FINANCIALLY_INVALIDATED"
