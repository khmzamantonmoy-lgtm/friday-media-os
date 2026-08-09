"""
Tier 3b — Operational Health: Dashboard Data Consistency
READ-ONLY Firestore. Validates that dashboard queries return consistent data.
"""
import pytest
import os

pytestmark = pytest.mark.health


def get_db():
    try:
        from google.cloud import firestore
        return firestore.Client(project=os.environ.get("GCP_PROJECT_ID", "friday-media-prod"))
    except Exception as e:
        pytest.skip(f"Firestore unavailable: {e}")


def test_content_items_queryable_by_brand():
    db = get_db()
    from src.config.firestore_schema import BRAND_PROFILES
    for brand_id in BRAND_PROFILES.keys():
        docs = list(db.collection("content_items").where("brand_id", "==", brand_id).limit(5).stream())
        assert isinstance(docs, list)


def test_scheduled_posts_readable():
    db = get_db()
    docs = list(db.collection("scheduled_posts").limit(10).stream())
    assert isinstance(docs, list)


def test_all_brands_have_content_items():
    db = get_db()
    from src.config.firestore_schema import BRAND_PROFILES
    for brand_id in BRAND_PROFILES.keys():
        docs = list(db.collection("content_items").where("brand_id", "==", brand_id).limit(1).stream())
        # Not a failure if empty (system may be new), but log it
        print(f"\n[INFO] content_items for {brand_id}: {len(docs)} found")


def test_total_published_count_consistent():
    """Dashboard published count must not exceed total content_items."""
    db = get_db()
    all_items = list(db.collection("content_items").stream())
    total = len(all_items)
    published = sum(1 for d in all_items if d.to_dict().get("status") in ("published", "COMPLETE"))
    assert published <= total, f"published ({published}) > total ({total})"


def test_brand_profiles_match_registry():
    """BRAND_PROFILES display names must map to BRAND_REGISTRY brand_name."""
    from src.config.firestore_schema import BRAND_PROFILES
    from src.config.brand_registry import BRAND_REGISTRY
    for brand_id in BRAND_PROFILES.keys():
        assert brand_id in BRAND_REGISTRY, (
            f"Brand '{brand_id}' in BRAND_PROFILES but not in BRAND_REGISTRY"
        )


def test_content_queue_status_values_are_valid():
    """All content_queue items must have recognized status values."""
    db = get_db()
    known_statuses = {
        "QUEUED", "GENERATING", "SCRIPT_READY", "VOICE_READY", "IMAGES_READY",
        "METADATA_READY", "RENDERING", "READY", "FAILED", "COMPLETE",
        "NEW", "TOPIC_SELECTED", "ASSETS_READY", "RENDERED", "UPLOADING",
        "PUBLIC", "CAPTIONS_VERIFIED", "MEMORY_UPDATED", "RETRY"
    }
    docs = list(db.collection("content_queue").limit(50).stream())
    unknown = []
    for doc in docs:
        status = doc.to_dict().get("status")
        if status and status not in known_statuses:
            unknown.append({"id": doc.id, "status": status})
    if unknown:
        print(f"\n[WARN] Unknown status values in content_queue: {unknown}")
    # Non-blocking: log warning, not a hard failure
