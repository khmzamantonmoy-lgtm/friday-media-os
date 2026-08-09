"""
Tier 2 — Integration: Goal Engine
Firestore and BrandWorker fully mocked.
"""
import pytest
import datetime
from unittest.mock import patch, MagicMock, call

def _make_doc(status, youtube_video_id=None, youtube_verified=False, created_at=None):
    doc = MagicMock()
    if not created_at:
        created_at = datetime.datetime.now(datetime.UTC).isoformat()
    data = {"status": status, "brand_id": "bd_threatpulse", "created_at": created_at}
    if youtube_video_id:
        data["youtube_video_id"] = youtube_video_id
    if youtube_verified:
        data["youtube_verified"] = True
    doc.to_dict.return_value = data
    return doc

def _make_db_with_docs(docs):
    db = MagicMock()
    query = MagicMock()
    query.stream.return_value = iter(docs)
    db.collection.return_value.where.return_value = query
    return db

@patch("src.engine.goal_engine.BrandWorker")
@patch("src.engine.goal_engine.firestore")
def test_unknown_brand_logs_error_no_exception(mock_fs, mock_worker):
    mock_fs.Client.return_value = MagicMock()
    from src.engine.goal_engine import GoalEngine
    engine = GoalEngine()
    engine.evaluate("nonexistent_brand")

@patch("src.engine.goal_engine.BrandWorker")
@patch("src.engine.goal_engine.firestore")
def test_zero_missing_no_worker_calls(mock_fs, MockWorker):
    docs = [_make_doc("COMPLETE", youtube_video_id="vid1", youtube_verified=True) for _ in range(4)]
    db = _make_db_with_docs(docs)
    mock_fs.Client.return_value = db
    mock_instance = MockWorker.return_value
    from src.engine.goal_engine import GoalEngine
    engine = GoalEngine()
    engine.evaluate("bd_threatpulse")
    mock_instance.run_cycle.assert_not_called()

@patch("src.engine.goal_engine.BrandWorker")
@patch("src.engine.goal_engine.firestore")
def test_one_missing_triggers_one_cycle(mock_fs, MockWorker):
    docs = [_make_doc("COMPLETE", youtube_video_id=f"vid{i}", youtube_verified=True) for i in range(3)]
    db = _make_db_with_docs(docs)
    mock_fs.Client.return_value = db
    mock_instance = MockWorker.return_value
    from src.engine.goal_engine import GoalEngine
    engine = GoalEngine()
    engine.evaluate("bd_threatpulse")
    assert mock_instance.run_cycle.call_count == 1

@patch("src.engine.goal_engine.BrandWorker")
@patch("src.engine.goal_engine.firestore")
def test_four_missing_triggers_four_cycles(mock_fs, MockWorker):
    db = _make_db_with_docs([])
    mock_fs.Client.return_value = db
    mock_instance = MockWorker.return_value
    from src.engine.goal_engine import GoalEngine
    engine = GoalEngine()
    engine.evaluate("bd_threatpulse")
    assert mock_instance.run_cycle.call_count == 4

@patch("src.engine.goal_engine.BrandWorker")
@patch("src.engine.goal_engine.firestore")
def test_active_items_reduce_missing(mock_fs, MockWorker):
    docs = [
        _make_doc("COMPLETE", youtube_video_id="vid1", youtube_verified=True),
        _make_doc("COMPLETE", youtube_video_id="vid2", youtube_verified=True),
        _make_doc("RENDERING"),
    ]
    db = _make_db_with_docs(docs)
    mock_fs.Client.return_value = db
    mock_instance = MockWorker.return_value
    from src.engine.goal_engine import GoalEngine
    engine = GoalEngine()
    engine.evaluate("bd_threatpulse")
    assert mock_instance.run_cycle.call_count == 1

@patch("src.engine.goal_engine.BrandWorker")
@patch("src.engine.goal_engine.firestore")
def test_unverified_complete_not_counted(mock_fs, MockWorker):
    docs = [
        _make_doc("COMPLETE"),  # unverified -> not counted towards verified
        _make_doc("COMPLETE"),
        _make_doc("COMPLETE"),
        _make_doc("COMPLETE"),
    ]
    db = _make_db_with_docs(docs)
    mock_fs.Client.return_value = db
    mock_instance = MockWorker.return_value
    from src.engine.goal_engine import GoalEngine
    engine = GoalEngine()
    engine.evaluate("bd_threatpulse")
    # Unverified items don't satisfy the goal -> missing is 4
    assert mock_instance.run_cycle.call_count == 4

@patch("src.engine.goal_engine.BrandWorker")
@patch("src.engine.goal_engine.firestore")
def test_failed_items_not_counted(mock_fs, MockWorker):
    docs = [_make_doc("FAILED") for _ in range(4)]
    db = _make_db_with_docs(docs)
    mock_fs.Client.return_value = db
    mock_instance = MockWorker.return_value
    from src.engine.goal_engine import GoalEngine
    engine = GoalEngine()
    engine.evaluate("bd_threatpulse")
    assert mock_instance.run_cycle.call_count == 4

@patch("src.engine.goal_engine.BrandWorker")
@patch("src.engine.goal_engine.firestore")
def test_missing_clamped_at_zero(mock_fs, MockWorker):
    docs = [_make_doc("COMPLETE", youtube_video_id=f"v{i}", youtube_verified=True) for i in range(5)]
    db = _make_db_with_docs(docs)
    mock_fs.Client.return_value = db
    mock_instance = MockWorker.return_value
    from src.engine.goal_engine import GoalEngine
    engine = GoalEngine()
    engine.evaluate("bd_threatpulse")
    mock_instance.run_cycle.assert_not_called()

@patch("src.engine.goal_engine.BrandWorker")
@patch("src.engine.goal_engine.firestore")
def test_worker_exception_logged_not_raised(mock_fs, MockWorker):
    db = _make_db_with_docs([])
    mock_fs.Client.return_value = db
    mock_instance = MockWorker.return_value
    mock_instance.run_cycle.side_effect = Exception("worker crash")
    from src.engine.goal_engine import GoalEngine
    engine = GoalEngine()
    engine.evaluate("bd_threatpulse")

@patch("src.engine.goal_engine.BrandWorker")
@patch("src.engine.goal_engine.firestore")
def test_daily_boundary_used(mock_fs, MockWorker):
    db = MagicMock()
    today = datetime.datetime.now(datetime.UTC).isoformat()
    yesterday = (datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=1)).isoformat()
    docs = [
        _make_doc("COMPLETE", youtube_video_id="vid1", youtube_verified=True, created_at=today),
        _make_doc("COMPLETE", youtube_video_id="vid2", youtube_verified=True, created_at=yesterday),
    ]
    query = MagicMock()
    query.stream.return_value = iter(docs)
    db.collection.return_value.where.return_value = query
    mock_fs.Client.return_value = db
    mock_instance = MockWorker.return_value
    from src.engine.goal_engine import GoalEngine
    engine = GoalEngine()
    engine.evaluate("bd_threatpulse")
    # Target=4, today=1 verified, yesterday is filtered out -> missing=3 -> 3 run_cycle calls
    assert mock_instance.run_cycle.call_count == 3

@patch("src.engine.goal_engine.BrandWorker")
@patch("src.engine.goal_engine.firestore")
def test_published_status_not_active(mock_fs, MockWorker):
    docs = [_make_doc("PUBLISHED") for _ in range(4)]
    db = _make_db_with_docs(docs)
    mock_fs.Client.return_value = db
    mock_instance = MockWorker.return_value
    from src.engine.goal_engine import GoalEngine
    engine = GoalEngine()
    engine.evaluate("bd_threatpulse")
    assert mock_instance.run_cycle.call_count == 4

@patch("src.engine.goal_engine.BrandWorker")
@patch("src.engine.goal_engine.firestore")
def test_scheduled_status_not_active(mock_fs, MockWorker):
    docs = [_make_doc("SCHEDULED") for _ in range(4)]
    db = _make_db_with_docs(docs)
    mock_fs.Client.return_value = db
    mock_instance = MockWorker.return_value
    from src.engine.goal_engine import GoalEngine
    engine = GoalEngine()
    engine.evaluate("bd_threatpulse")
    assert mock_instance.run_cycle.call_count == 4

@patch("src.engine.goal_engine.BrandWorker")
@patch("src.engine.goal_engine.firestore")
def test_ready_status_not_active(mock_fs, MockWorker):
    docs = [_make_doc("READY") for _ in range(4)]
    db = _make_db_with_docs(docs)
    mock_fs.Client.return_value = db
    mock_instance = MockWorker.return_value
    from src.engine.goal_engine import GoalEngine
    engine = GoalEngine()
    engine.evaluate("bd_threatpulse")
    assert mock_instance.run_cycle.call_count == 4

@patch("src.engine.goal_engine.BrandWorker")
@patch("src.engine.goal_engine.firestore")
def test_genuinely_running_work_is_active(mock_fs, MockWorker):
    docs = [
        _make_doc("NEW"),
        _make_doc("RENDERING"),
        _make_doc("UPLOADING"),
    ]
    db = _make_db_with_docs(docs)
    mock_fs.Client.return_value = db
    mock_instance = MockWorker.return_value
    from src.engine.goal_engine import GoalEngine
    engine = GoalEngine()
    engine.evaluate("bd_threatpulse")
    # 3 active in-flight jobs -> missing = 4 - 3 = 1
    assert mock_instance.run_cycle.call_count == 1
