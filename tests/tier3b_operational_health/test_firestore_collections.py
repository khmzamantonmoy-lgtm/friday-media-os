"""
Tier 3b — Operational Health: Firestore Collection Accessibility
READ-ONLY. Zero writes.
"""
import pytest
import os
import datetime

pytestmark = pytest.mark.health


def get_db():
    try:
        from google.cloud import firestore
        return firestore.Client(project=os.environ.get("GCP_PROJECT_ID", "friday-media-prod"))
    except Exception as e:
        pytest.skip(f"Firestore unavailable: {e}")


def test_content_queue_is_accessible():
    db = get_db()
    try:
        docs = list(db.collection("content_queue").limit(1).stream())
        assert isinstance(docs, list)
    except Exception as e:
        pytest.fail(f"content_queue not accessible: {e}")


def test_content_items_is_accessible():
    db = get_db()
    try:
        docs = list(db.collection("content_items").limit(1).stream())
        assert isinstance(docs, list)
    except Exception as e:
        pytest.fail(f"content_items not accessible: {e}")


@pytest.mark.parametrize("brand_id", ["bd_threatpulse", "wealthwise", "kids_universe", "philosophy"])
def test_brand_memory_exists(brand_id):
    db = get_db()
    doc = db.collection("brand_memory").document(brand_id).get()
    assert doc.exists, f"brand_memory/{brand_id} does not exist in Firestore"


def test_production_metrics_collection_accessible():
    db = get_db()
    try:
        docs = list(db.collection("production_metrics").limit(1).stream())
        assert isinstance(docs, list)
    except Exception as e:
        pytest.fail(f"production_metrics not accessible: {e}")


def test_scheduled_posts_accessible():
    db = get_db()
    try:
        docs = list(db.collection("scheduled_posts").limit(1).stream())
        assert isinstance(docs, list)
    except Exception as e:
        pytest.fail(f"scheduled_posts not accessible: {e}")


def test_no_items_stuck_in_non_terminal_over_2h():
    db = get_db()
    two_hours_ago = (datetime.datetime.utcnow() - datetime.timedelta(hours=2)).isoformat()
    terminal = {"COMPLETE", "FAILED", "published", "failed"}
    stuck = []
    for doc in db.collection("content_items").stream():
        data = doc.to_dict()
        status = data.get("status", "")
        if status in terminal:
            continue
        created_at = data.get("created_at")
        if created_at:
            ca_str = created_at.isoformat() if hasattr(created_at, "isoformat") else str(created_at)
            if ca_str < two_hours_ago:
                stuck.append({"id": doc.id, "status": status})
    assert len(stuck) == 0, f"Stuck items found (>2h, non-terminal): {stuck}"


def test_dead_letter_queue_accessible():
    db = get_db()
    try:
        docs = list(db.collection("dead_letter_queue").limit(5).stream())
        # Report count as informational (not a failure if items exist)
        print(f"\n[INFO] dead_letter_queue items: {len(docs)}")
        assert isinstance(docs, list)
    except Exception as e:
        pytest.fail(f"dead_letter_queue not accessible: {e}")


def test_content_items_have_required_fields():
    """Spot-check: last 10 content_items have required fields."""
    db = get_db()
    try:
        docs = list(
            db.collection("content_items")
            .order_by("created_at", direction="DESCENDING")
            .limit(10)
            .stream()
        )
    except Exception:
        docs = list(db.collection("content_items").limit(10).stream())
    required = {"brand_id", "topic", "status"}
    for doc in docs:
        data = doc.to_dict()
        missing = required - set(data.keys())
        assert not missing, f"content_item {doc.id} missing fields: {missing}"
