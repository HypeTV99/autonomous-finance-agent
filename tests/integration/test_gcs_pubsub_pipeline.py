import base64
import json
import uuid
from firestore_store import FirestoreStateStore

def test_pubsub_at_least_once_deduplication():
    store = FirestoreStateStore()
    uid = uuid.uuid4().hex[:8]
    doc_digest = f"digest_event_pubsub_{uid}"
    inv_num = f"INV-PUBSUB-DEDUP-{uid}"

    # 1. First event arrival
    assert store.is_already_processed(doc_digest) is False
    store.mark_processed(doc_digest, inv_num, business_key=f"PAN_{inv_num}_FY26")
    assert store.is_already_processed(doc_digest) is True

    # 2. Duplicate redelivery (PubSub at-least-once) -> Already processed
    assert store.is_already_processed(doc_digest) is True
