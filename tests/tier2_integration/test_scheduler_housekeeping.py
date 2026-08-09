"""
Tier 2 — Integration: Scheduler Housekeeping
Firestore and GoalEngine fully mocked.
"""
import pytest
import datetime
from unittest.mock import patch, MagicMock, call


def _make_content_doc(status, created_at_delta_hours=0, youtube_verified=False, youtube_video_id=None):
    doc = MagicMock()
    created_at = (datetime.datetime.utcnow() - datetime.timedelta(hours=created_at_delta_hours)).isoformat()
    data = {"status": status, "created_at": created_at}
    if youtube_verified:
        data["youtube_verified"] = True
    if youtube_video_id:
        data["youtube_video_id"] = youtube_video_id
    doc.to_dict.return_value = data
    doc.reference = MagicMock()
    return doc


@patch("src.scheduler.autonomous_scheduler.GoalEngine")
@patch("src.scheduler.autonomous_scheduler.firestore")
def test_stale_item_marked_failed(mock_fs, mock_ge):
    stale_doc = _make_content_doc("NEW", created_at_delta_hours=3)
    db = MagicMock()
    db.collection.return_value.where.return_value.stream.return_value = iter([stale_doc])
    mock_fs.Client.return_value = db
    from src.scheduler.autonomous_scheduler import run_scheduler
    run_scheduler()
    stale_doc.reference.update.assert_called()
    update_data = stale_doc.reference.update.call_args.args[0]
    assert update_data.get("status") == "FAILED"


@patch("src.scheduler.autonomous_scheduler.GoalEngine")
@patch("src.scheduler.autonomous_scheduler.firestore")
def test_fresh_item_not_touched(mock_fs, mock_ge):
    fresh_doc = _make_content_doc("NEW", created_at_delta_hours=0.1)  # 6 minutes old
    db = MagicMock()
    db.collection.return_value.where.return_value.stream.return_value = iter([fresh_doc])
    mock_fs.Client.return_value = db
    from src.scheduler.autonomous_scheduler import run_scheduler
    run_scheduler()
    # No FAILED update should have been called for this doc
    if fresh_doc.reference.update.called:
        calls_data = [c.args[0] for c in fresh_doc.reference.update.call_args_list]
        for d in calls_data:
            assert d.get("status") != "FAILED", "Fresh item should not be marked FAILED"


@patch("src.scheduler.autonomous_scheduler.GoalEngine")
@patch("src.scheduler.autonomous_scheduler.firestore")
def test_false_verified_flag_reset(mock_fs, mock_ge):
    """youtube_verified=True but no youtube_video_id -> flag must be reset."""
    bad_doc = _make_content_doc("COMPLETE", created_at_delta_hours=0.1, youtube_verified=True)
    db = MagicMock()
    db.collection.return_value.where.return_value.stream.return_value = iter([bad_doc])
    mock_fs.Client.return_value = db
    from src.scheduler.autonomous_scheduler import run_scheduler
    run_scheduler()
    calls_data = [c.args[0] for c in bad_doc.reference.update.call_args_list]
    assert any(d.get("youtube_verified") is False for d in calls_data), (
        "youtube_verified should be reset when youtube_video_id is absent"
    )


@patch("src.scheduler.autonomous_scheduler.GoalEngine")
@patch("src.scheduler.autonomous_scheduler.firestore")
def test_correct_verified_flag_preserved(mock_fs, mock_ge):
    """youtube_verified=True WITH youtube_video_id -> do NOT touch the flag."""
    good_doc = _make_content_doc("COMPLETE", created_at_delta_hours=0.1,
                                 youtube_verified=True, youtube_video_id="abc123")
    db = MagicMock()
    db.collection.return_value.where.return_value.stream.return_value = iter([good_doc])
    mock_fs.Client.return_value = db
    from src.scheduler.autonomous_scheduler import run_scheduler
    run_scheduler()
    if good_doc.reference.update.called:
        calls_data = [c.args[0] for c in good_doc.reference.update.call_args_list]
        for d in calls_data:
            assert "youtube_verified" not in d or d["youtube_verified"] is not False


@patch("src.scheduler.autonomous_scheduler.GoalEngine")
@patch("src.scheduler.autonomous_scheduler.firestore")
def test_housekeeping_exception_does_not_crash_scheduler(mock_fs, mock_ge):
    db = MagicMock()
    db.collection.side_effect = Exception("Firestore unavailable")
    mock_fs.Client.return_value = db
    mock_engine_instance = mock_ge.return_value
    mock_engine_instance.count_for_brand.return_value = {"missing": 0, "verified": 0, "active": 0, "daily_target": 1}
    from src.scheduler.autonomous_scheduler import run_scheduler
    run_scheduler()  # Must not raise
    # GoalEngine should still be attempted for each brand
    assert mock_engine_instance.count_for_brand.called


@patch("src.scheduler.autonomous_scheduler.GoalEngine")
@patch("src.scheduler.autonomous_scheduler.firestore")
def test_all_four_brands_evaluated(mock_fs, mock_ge):
    db = MagicMock()
    db.collection.return_value.where.return_value.stream.return_value = iter([])
    mock_fs.Client.return_value = db
    mock_engine_instance = mock_ge.return_value
    mock_engine_instance.count_for_brand.return_value = {"missing": 0, "verified": 0, "active": 0, "daily_target": 1}
    from src.scheduler.autonomous_scheduler import run_scheduler
    from src.config.brand_registry import BRAND_REGISTRY
    run_scheduler()
    assert mock_engine_instance.count_for_brand.call_count == len(BRAND_REGISTRY)
    called_brands = [c.args[0] for c in mock_engine_instance.count_for_brand.call_args_list]
    for brand_id in BRAND_REGISTRY.keys():
        assert brand_id in called_brands, f"Brand {brand_id} not evaluated"


@patch("src.scheduler.autonomous_scheduler.GoalEngine")
@patch("src.scheduler.autonomous_scheduler.firestore")
def test_brand_error_does_not_stop_others(mock_fs, mock_ge):
    db = MagicMock()
    db.collection.return_value.where.return_value.stream.return_value = iter([])
    mock_fs.Client.return_value = db
    mock_engine_instance = mock_ge.return_value
    call_count = []
    def count_side_effect(brand_id):
        call_count.append(brand_id)
        if brand_id == "bd_threatpulse":
            raise Exception("Brand A crashed")
        return {"missing": 0, "verified": 0, "active": 0, "daily_target": 1}
    mock_engine_instance.count_for_brand.side_effect = count_side_effect
    from src.scheduler.autonomous_scheduler import run_scheduler
    from src.config.brand_registry import BRAND_REGISTRY
    run_scheduler()  # Must not raise
    assert len(call_count) == len(BRAND_REGISTRY), "All brands must be attempted"

