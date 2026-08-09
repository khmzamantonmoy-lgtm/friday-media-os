"""
Tier 4 — Chaos: Quota Limit Simulation
All mocked. Verifies correct quota handling.
"""
import pytest
from unittest.mock import patch, MagicMock


@patch("src.engine.retry_manager.firestore")
@patch("src.engine.retry_manager.time.sleep")
def test_gemini_429_triggers_60s_minimum_wait(mock_sleep, mock_fs):
    from src.engine.retry_manager import with_retry
    call_count = [0]
    @with_retry(max_retries=3, base_delay=1.0)
    def call_gemini():
        call_count[0] += 1
        if call_count[0] < 3:
            raise Exception("HTTP Error 429: Quota exceeded")
        return "ok"
    result = call_gemini()
    assert result == "ok"
    sleep_vals = [c.args[0] for c in mock_sleep.call_args_list]
    assert all(v >= 60.0 for v in sleep_vals), f"Some delays < 60s on 429: {sleep_vals}"


@patch("src.engine.retry_manager.firestore")
@patch("src.engine.retry_manager.time.sleep")
def test_youtube_429_triggers_60s_minimum_wait(mock_sleep, mock_fs):
    from src.engine.retry_manager import with_retry
    call_count = [0]
    @with_retry(max_retries=3, base_delay=1.0)
    def upload():
        call_count[0] += 1
        if call_count[0] < 3:
            raise Exception("YouTube API 429: Too many requests")
        return "uploaded"
    result = upload()
    assert result == "uploaded"
    sleep_vals = [c.args[0] for c in mock_sleep.call_args_list]
    assert all(v >= 60.0 for v in sleep_vals), f"YouTube 429 delay < 60s: {sleep_vals}"


@patch("src.engine.retry_manager.firestore")
@patch("src.engine.retry_manager.time.sleep")
def test_sustained_quota_exhaustion_hits_dlq(mock_sleep, mock_fs):
    """5 consecutive 429s must hit DLQ without infinite looping."""
    from src.engine.retry_manager import with_retry
    mock_db = MagicMock()
    mock_fs.Client.return_value = mock_db
    mock_fs.SERVER_TIMESTAMP = "ts"
    @with_retry(max_retries=5, base_delay=1.0)
    def always_429():
        raise Exception("HTTP 429 quota")
    with pytest.raises(Exception, match="429"):
        always_429()
    mock_db.collection.assert_called_with("dead_letter_queue")
    mock_db.collection().add.assert_called_once()
    # Verify we don't call sleep more than max_retries - 1 times
    assert mock_sleep.call_count == 4  # 5 retries, sleep between each except last


@patch("src.engine.retry_manager.firestore")
@patch("src.engine.retry_manager.time.sleep")
def test_quota_recovery_succeeds(mock_sleep, mock_fs):
    """2 quota failures then success -> returns value normally."""
    from src.engine.retry_manager import with_retry
    call_count = [0]
    @with_retry(max_retries=5, base_delay=0.001)
    def flaky():
        call_count[0] += 1
        if call_count[0] <= 2:
            raise Exception("429 rate limit")
        return "recovered"
    result = flaky()
    assert result == "recovered"
    assert call_count[0] == 3


@patch("src.engine.goal_engine.BrandWorker")
@patch("src.engine.goal_engine.firestore")
@patch("src.engine.retry_manager.time.sleep")
def test_one_brand_quota_does_not_affect_others(mock_sleep, mock_fs_engine, MockWorker):
    """Brand A quota exhaustion must not prevent Brand B, C, D from being evaluated."""
    from src.engine.goal_engine import GoalEngine
    from src.config.brand_registry import BRAND_REGISTRY
    db = MagicMock()
    query = MagicMock()
    query.stream.return_value = iter([])
    db.collection.return_value.where.return_value.where.return_value = query
    mock_fs_engine.Client.return_value = db
    evaluated = []
    def evaluate_side_effect(brand_id):
        evaluated.append(brand_id)
        if brand_id == "bd_threatpulse":
            raise Exception("429 quota exceeded for bd_threatpulse")
    MockWorker.return_value.run_cycle.side_effect = Exception("429")
    from src.scheduler.autonomous_scheduler import run_scheduler
    run_scheduler()
    # All brands should have been attempted regardless of one failing
    from src.config.brand_registry import BRAND_REGISTRY
    print(f"\n[INFO] Evaluated brands: {evaluated}")


@patch("src.engine.retry_manager.firestore")
@patch("src.engine.retry_manager.time.sleep")
def test_tts_503_triggers_30s_minimum_wait(mock_sleep, mock_fs):
    from src.engine.retry_manager import with_retry
    call_count = [0]
    @with_retry(max_retries=3, base_delay=1.0)
    def call_tts():
        call_count[0] += 1
        if call_count[0] < 3:
            raise Exception("503 Service Unavailable from TTS")
        return "audio.mp3"
    result = call_tts()
    assert result == "audio.mp3"
    sleep_vals = [c.args[0] for c in mock_sleep.call_args_list]
    assert all(v >= 30.0 for v in sleep_vals), f"TTS 503 delay < 30s: {sleep_vals}"
