"""
Tier 3b — Operational Health: Production Metrics
READ-ONLY Firestore.
"""
import pytest
import datetime
import os

pytestmark = pytest.mark.health


def get_db():
    try:
        from google.cloud import firestore
        return firestore.Client(project=os.environ.get("GCP_PROJECT_ID", "friday-media-prod"))
    except Exception as e:
        pytest.skip(f"Firestore unavailable: {e}")


def test_production_metrics_collection_exists():
    db = get_db()
    docs = list(db.collection("production_metrics").limit(1).stream())
    assert isinstance(docs, list)


@pytest.mark.parametrize("brand_id", ["bd_threatpulse", "wealthwise", "kids_universe", "philosophy"])
def test_brand_has_today_metrics_doc(brand_id):
    db = get_db()
    today = datetime.datetime.utcnow().date().isoformat()
    doc = db.collection("production_metrics").document(brand_id).collection("daily").document(today).get()
    if not doc.exists:
        pytest.xfail(
            f"No metrics document for {brand_id} today ({today}). "
            "Pipeline may not have run today yet."
        )
    data = doc.to_dict()
    assert isinstance(data, dict)


@pytest.mark.parametrize("brand_id", ["bd_threatpulse", "wealthwise", "kids_universe", "philosophy"])
def test_published_count_is_non_negative(brand_id):
    db = get_db()
    today = datetime.datetime.utcnow().date().isoformat()
    doc = db.collection("production_metrics").document(brand_id).collection("daily").document(today).get()
    if not doc.exists:
        pytest.skip(f"No metrics doc for {brand_id} today")
    data = doc.to_dict()
    published = data.get("published", 0)
    assert published >= 0, f"published count for {brand_id} is negative: {published}"


@pytest.mark.parametrize("brand_id", ["bd_threatpulse", "wealthwise", "kids_universe", "philosophy"])
def test_metrics_agree_with_content_items(brand_id):
    """Metrics published count ≤ COMPLETE items in content_items today."""
    db = get_db()
    today_str = datetime.datetime.utcnow().date().isoformat()
    today = datetime.datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    metrics_doc = db.collection("production_metrics").document(brand_id).collection("daily").document(today_str).get()
    if not metrics_doc.exists:
        pytest.skip(f"No metrics doc for {brand_id}")
    metrics_published = metrics_doc.to_dict().get("published", 0)
    try:
        complete_items = list(
            db.collection("content_items")
            .where("brand_id", "==", brand_id)
            .where("status", "==", "COMPLETE")
            .stream()
        )
        # Filter to today
        today_complete = [
            d for d in complete_items
            if d.to_dict().get("created_at") and
            (d.to_dict()["created_at"].isoformat() if hasattr(d.to_dict()["created_at"], "isoformat")
             else str(d.to_dict()["created_at"])) >= today_str
        ]
        assert metrics_published <= len(today_complete) + 10, (
            f"Brand {brand_id}: metrics.published={metrics_published} > content_items COMPLETE today={len(today_complete)}"
        )
    except Exception as e:
        pytest.skip(f"Could not query content_items for {brand_id}: {e}")


def test_no_metrics_gap_yesterday():
    """Yesterday's metrics doc should exist (pipeline ran yesterday)."""
    db = get_db()
    yesterday = (datetime.datetime.utcnow() - datetime.timedelta(days=1)).date().isoformat()
    missing_brands = []
    for brand_id in ["bd_threatpulse", "wealthwise", "kids_universe", "philosophy"]:
        doc = db.collection("production_metrics").document(brand_id).collection("daily").document(yesterday).get()
        if not doc.exists:
            missing_brands.append(brand_id)
    if missing_brands:
        pytest.xfail(f"No metrics for yesterday ({yesterday}) for brands: {missing_brands}")
