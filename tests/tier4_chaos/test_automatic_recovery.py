"""
Tier 4 — Chaos: Automatic Recovery Scenarios
Verifies the system recovers autonomously from transient failures
without manual intervention.
All mocked.
"""
import pytest
from unittest.mock import patch, MagicMock


@patch("src.engine.retry_manager.firestore")
@patch("src.engine.retry_manager.time.sleep")
def test_script_failure_then_recovery(mock_sleep, mock_fs):
    """Script generation fails twice, succeeds on third attempt — returns value."""
    from src.engine.retry_manager import with_retry
    call_count = [0]
    @with_retry(max_retries=5, base_delay=0.001)
    def gen_script():
        call_count[0] += 1
        if call_count[0] < 3:
            raise Exception("Gemini timeout")
        return {"narration": "Test script", "visual_prompts": []}
    result = gen_script()
    assert result["narration"] == "Test script"
    assert call_count[0] == 3


@patch("src.engine.retry_manager.firestore")
@patch("src.engine.retry_manager.time.sleep")
def test_upload_failure_then_recovery(mock_sleep, mock_fs):
    """Upload fails once (503), succeeds on retry."""
    from src.engine.retry_manager import with_retry
    call_count = [0]
    @with_retry(max_retries=3, base_delay=0.001)
    def upload():
        call_count[0] += 1
        if call_count[0] == 1:
            raise Exception("503 YouTube service temporarily unavailable")
        return "https://youtube.com/watch?v=recovered"
    result = upload()
    assert "recovered" in result
    assert call_count[0] == 2


@patch("src.engine.goal_engine.BrandWorker")
@patch("src.engine.goal_engine.firestore")
def test_goal_engine_relaunches_after_worker_crash(mock_fs, MockWorker):
    """If a worker cycle crashes, GoalEngine still launches the remaining missing cycles."""
    crash_count = [0]
    def side_effect(brand_id):
        crash_count[0] += 1
        if crash_count[0] == 1:
            raise Exception("Worker crashed")
        # Subsequent calls succeed silently
    MockWorker.return_value.run_cycle.side_effect = side_effect
    db = MagicMock()
    query = MagicMock()
    query.stream.return_value = iter([])  # 0 verified -> missing=4
    db.collection.return_value.where.return_value.where.return_value = query
    mock_fs.Client.return_value = db
    from src.engine.goal_engine import GoalEngine
    engine = GoalEngine()
    engine.evaluate("bd_threatpulse")
    # All 4 cycles should be attempted even though first one crashed
    assert MockWorker.return_value.run_cycle.call_count == 4


@patch("src.engine.retry_manager.firestore")
@patch("src.engine.retry_manager.time.sleep")
def test_image_generation_recovery(mock_sleep, mock_fs):
    """Image generation fails with quota error, recovers on second attempt."""
    from src.engine.retry_manager import with_retry
    call_count = [0]
    @with_retry(max_retries=4, base_delay=0.001)
    def gen_images():
        call_count[0] += 1
        if call_count[0] == 1:
            raise Exception("429 Imagen quota exceeded")
        return ["gs://bucket/img1.png", "gs://bucket/img2.png"]
    result = gen_images()
    assert len(result) == 2
    assert call_count[0] == 2


@patch("src.engine.retry_manager.firestore")
@patch("src.engine.retry_manager.time.sleep")
def test_render_failure_then_recovery(mock_sleep, mock_fs):
    """Render fails once then succeeds."""
    from src.engine.retry_manager import with_retry
    call_count = [0]
    @with_retry(max_retries=3, base_delay=0.001)
    def render():
        call_count[0] += 1
        if call_count[0] == 1:
            raise Exception("FFmpeg render error")
        return ("gs://bucket/video.mp4", "gs://bucket/subs.srt")
    result = render()
    assert result[0].endswith(".mp4")


@patch("src.scheduler.autonomous_scheduler.GoalEngine")
@patch("src.scheduler.autonomous_scheduler.firestore")
def test_scheduler_restart_resumes_missing_slots(mock_fs, MockGoalEngine):
    """On restart with 1 COMPLETE and 0 active, scheduler finds 3 missing and resumes."""
    db = MagicMock()
    db.collection.return_value.where.return_value.stream.return_value = iter([])
    mock_fs.Client.return_value = db
    mock_engine = MockGoalEngine.return_value
    from src.scheduler.autonomous_scheduler import run_scheduler
    run_scheduler()
    assert mock_engine.evaluate.called, "GoalEngine.evaluate must be called on scheduler restart"


@patch("src.engine.retry_manager.firestore")
@patch("src.engine.retry_manager.time.sleep")
def test_dlq_write_failure_does_not_block_recovery(mock_sleep, mock_fs):
    """If DLQ write fails, the original exception still propagates (no silent swallow)."""
    from src.engine.retry_manager import with_retry
    mock_db = MagicMock()
    mock_fs.Client.return_value = mock_db
    mock_db.collection.side_effect = Exception("DLQ Firestore unavailable")
    @with_retry(max_retries=2, base_delay=0.001)
    def failing_fn():
        raise ValueError("Original failure")
    with pytest.raises(ValueError, match="Original failure"):
        failing_fn()


@patch("src.engine.retry_manager.firestore")
@patch("src.engine.retry_manager.time.sleep")
def test_verification_retry_eventually_passes(mock_sleep, mock_fs):
    """Verification failing twice then passing = correct recovery path."""
    from src.engine.retry_manager import with_retry
    call_count = [0]
    @with_retry(max_retries=5, base_delay=0.001)
    def verify():
        call_count[0] += 1
        if call_count[0] < 3:
            raise Exception("Video still processing")
        return True
    result = verify()
    assert result is True
    assert call_count[0] == 3
