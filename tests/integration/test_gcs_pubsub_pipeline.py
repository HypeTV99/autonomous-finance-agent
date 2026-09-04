import base64
import json
from firestore_store import FirestoreStateStore

def test_pubsub_at_least_once_deduplication():
    store = FirestoreStateStore()
    doc_digest = "digest_event_pubsub_001"
    inv_num = "INV-PUBSUB-DEDUP-01"

    # 1. First event arrival
    assert store.is_already_processed(doc_digest) is False
    store.mark_processed(doc_digest, inv_num, business_key=f"PAN_{inv_num}_FY26")
    assert store.is_already_processed(doc_digest) is True

    # 2. Duplicate redelivery (PubSub at-least-once) -> Already processed
    assert store.is_already_processed(doc_digest) is True
