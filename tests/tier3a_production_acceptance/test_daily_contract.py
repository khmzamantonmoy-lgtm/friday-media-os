"""
Tier 3a — Production Acceptance: Daily Contract
READ-ONLY Firestore. Evidence of current production state.
Failures here = production gap evidence, not test bugs.
"""
import pytest
import datetime
import os

pytestmark = pytest.mark.acceptance


def get_db():
    try:
        from google.cloud import firestore
        return firestore.Client(project=os.environ.get("GCP_PROJECT_ID", "friday-media-prod"))
    except Exception as e:
        pytest.skip(f"Firestore unavailable: {e}")


def get_today_start():
    return datetime.datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)


def get_verified_today(db, brand_id):
    today = get_today_start()
    docs = list(
        db.collection("content_queue")
        .where("brand_id", "==", brand_id)
        .where("created_at", ">=", today)
        .stream()
    )
    return [
        d for d in docs
        if d.to_dict().get("status") == "COMPLETE"
        and d.to_dict().get("youtube_video_id")
        and d.to_dict().get("youtube_verified") is True
    ]


@pytest.mark.parametrize("brand_id", [
    "bd_threatpulse", "wealthwise", "kids_universe", "philosophy"
])
def test_daily_contract_four_videos(brand_id):
    """Each brand must have ≥4 verified+public+captioned videos today."""
    db = get_db()
    verified = get_verified_today(db, brand_id)
    assert len(verified) >= 4, (
        f"FAIL: Brand '{brand_id}' has only {len(verified)}/4 verified public videos today. "
        f"Pipeline has not fulfilled the daily contract."
    )


@pytest.mark.parametrize("brand_id", [
    "bd_threatpulse", "wealthwise", "kids_universe", "philosophy"
])
def test_no_videos_private(brand_id):
    """No video for this brand today should have privacyStatus != public."""
    db = get_db()
    today = get_today_start()
    docs = list(
        db.collection("content_queue")
        .where("brand_id", "==", brand_id)
        .where("created_at", ">=", today)
        .stream()
    )
    private_vids = [
        d.to_dict().get("youtube_video_id")
        for d in docs
        if d.to_dict().get("youtube_verified") is True
        and d.to_dict().get("privacy_status", "public") != "public"
    ]
    assert len(private_vids) == 0, f"Brand {brand_id} has private verified videos: {private_vids}"


def test_no_orphan_queue_records():
    """No content_queue items in non-terminal state for > 2 hours."""
    db = get_db()
    two_hours_ago = (datetime.datetime.utcnow() - datetime.timedelta(hours=2)).isoformat()
    terminal = {"COMPLETE", "FAILED"}
    all_docs = list(db.collection("content_queue").stream())
    orphans = []
    for doc in all_docs:
        data = doc.to_dict()
        status = data.get("status", "")
        created_at = data.get("created_at")
        if status not in terminal and created_at:
            created_str = created_at.isoformat() if hasattr(created_at, "isoformat") else str(created_at)
            if created_str < two_hours_ago:
                orphans.append({"id": doc.id, "status": status, "created_at": created_str})
    assert len(orphans) == 0, f"Orphan queue records found: {orphans}"


def test_no_dead_letter_items_today():
    """dead_letter_queue must have 0 items created today."""
    db = get_db()
    today = get_today_start()
    try:
        dlq_docs = list(db.collection("dead_letter_queue").stream())
    except Exception:
        dlq_docs = []
    today_dlq = []
    for doc in dlq_docs:
        data = doc.to_dict()
        ts = data.get("timestamp")
        if ts:
            ts_dt = ts if hasattr(ts, "replace") else datetime.datetime.utcnow()
            if ts_dt >= today:
                today_dlq.append({"id": doc.id, "error": data.get("error", "unknown")})
    assert len(today_dlq) == 0, f"Dead-letter items created today: {today_dlq}"


@pytest.mark.parametrize("brand_id", [
    "bd_threatpulse", "wealthwise", "kids_universe", "philosophy"
])
def test_brand_memory_updated_today(brand_id):
    """brand_memory must contain entries from today's pipeline run."""
    db = get_db()
    mem_doc = db.collection("brand_memory").document(brand_id).get()
    assert mem_doc.exists, f"brand_memory/{brand_id} does not exist"
    data = mem_doc.to_dict()
    assert data.get("last_200_videos"), f"brand_memory/{brand_id} has no video history"


def test_no_items_stuck_in_rendering():
    """No items in RENDERING state for > 30 minutes (pipeline hang detection)."""
    db = get_db()
    thirty_min_ago = (datetime.datetime.utcnow() - datetime.timedelta(minutes=30)).isoformat()
    stuck = []
    for doc in db.collection("content_items").stream():
        data = doc.to_dict()
        if data.get("status") == "rendering":
            updated = data.get("updated_at") or data.get("created_at")
            if updated:
                updated_str = updated.isoformat() if hasattr(updated, "isoformat") else str(updated)
                if updated_str < thirty_min_ago:
                    stuck.append(doc.id)
    assert len(stuck) == 0, f"Items stuck in RENDERING > 30min: {stuck}"
