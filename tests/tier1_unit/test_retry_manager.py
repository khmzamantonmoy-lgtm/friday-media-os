"""
Tier 1 — Unit: Retry Manager
All Firestore and time.sleep calls are mocked.
"""
import pytest
from unittest.mock import patch, MagicMock, call


def make_flaky(fail_count, return_value="ok"):
    """Returns a callable that fails `fail_count` times then returns value."""
    calls = []
    def fn(*args, **kwargs):
        calls.append(1)
        if len(calls) <= fail_count:
            raise Exception(f"Transient failure #{len(calls)}")
        return return_value
    return fn


@patch("src.engine.retry_manager.firestore")
@patch("src.engine.retry_manager.time.sleep")
def test_success_on_first_attempt(mock_sleep, mock_fs):
    from src.engine.retry_manager import with_retry
    counter = []
    @with_retry(max_retries=3, base_delay=1.0)
    def fn():
        counter.append(1)
        return "done"
    result = fn()
    assert result == "done"
    assert len(counter) == 1
    mock_sleep.assert_not_called()


@patch("src.engine.retry_manager.firestore")
@patch("src.engine.retry_manager.time.sleep")
def test_retry_on_transient_failure(mock_sleep, mock_fs):
    from src.engine.retry_manager import with_retry
    flaky = make_flaky(fail_count=2, return_value="success")
    @with_retry(max_retries=5, base_delay=0.001)
    def fn():
        return flaky()
    result = fn()
    assert result == "success"
    assert mock_sleep.call_count == 2


@patch("src.engine.retry_manager.firestore")
@patch("src.engine.retry_manager.time.sleep")
def test_http_429_enforces_minimum_60s(mock_sleep, mock_fs):
    from src.engine.retry_manager import with_retry
    @with_retry(max_retries=5, base_delay=1.0)
    def fn():
        raise Exception("HTTP 429 quota exceeded")
    try:
        fn()
    except Exception:
        pass
    sleep_args = [c.args[0] for c in mock_sleep.call_args_list]
    assert all(v >= 60.0 for v in sleep_args), f"Expected >=60s, got {sleep_args}"


@patch("src.engine.retry_manager.firestore")
@patch("src.engine.retry_manager.time.sleep")
def test_http_503_enforces_minimum_30s(mock_sleep, mock_fs):
    from src.engine.retry_manager import with_retry
    @with_retry(max_retries=5, base_delay=1.0)
    def fn():
        raise Exception("HTTP 503 service unavailable")
    try:
        fn()
    except Exception:
        pass
    sleep_args = [c.args[0] for c in mock_sleep.call_args_list]
    assert all(v >= 30.0 for v in sleep_args), f"Expected >=30s, got {sleep_args}"


@patch("src.engine.retry_manager.firestore")
@patch("src.engine.retry_manager.time.sleep")
def test_dead_letter_written_on_max_retries(mock_sleep, mock_fs):
    from src.engine.retry_manager import with_retry
    mock_db = MagicMock()
    mock_fs.Client.return_value = mock_db
    mock_fs.SERVER_TIMESTAMP = "ts"
    @with_retry(max_retries=3, base_delay=0.001)
    def fn():
        raise Exception("permanent failure")
    with pytest.raises(Exception, match="permanent failure"):
        fn()
    mock_db.collection.assert_called_with("dead_letter_queue")
    mock_db.collection().add.assert_called_once()


@patch("src.engine.retry_manager.firestore")
@patch("src.engine.retry_manager.time.sleep")
def test_exception_reraised_after_max_retries(mock_sleep, mock_fs):
    from src.engine.retry_manager import with_retry
    @with_retry(max_retries=2, base_delay=0.001)
    def fn():
        raise ValueError("boom")
    with pytest.raises(ValueError, match="boom"):
        fn()


@patch("src.engine.retry_manager.firestore")
@patch("src.engine.retry_manager.time.sleep")
def test_backoff_increases_per_attempt(mock_sleep, mock_fs):
    from src.engine.retry_manager import with_retry
    @with_retry(max_retries=4, base_delay=1.0)
    def fn():
        raise Exception("generic")
    try:
        fn()
    except Exception:
        pass
    delays = [c.args[0] for c in mock_sleep.call_args_list]
    assert len(delays) >= 2
    # Each delay should be >= previous (accounting for jitter: check min possible)
    assert delays[-1] > delays[0], f"Later delays should be larger: {delays}"


@patch("src.engine.retry_manager.firestore")
@patch("src.engine.retry_manager.time.sleep")
def test_jitter_within_bounds(mock_sleep, mock_fs):
    from src.engine.retry_manager import with_retry
    import random
    base = 1.0
    @with_retry(max_retries=2, base_delay=base)
    def fn():
        raise Exception("generic")
    try:
        fn()
    except Exception:
        pass
    for c in mock_sleep.call_args_list:
        delay = c.args[0]
        # delay = base * 2^attempt + jitter(0-2)
        # For attempt 0: base*1 + [0,2] = [1, 3]
        # For attempt 1: base*2 + [0,2] = [2, 4]
        assert delay >= base, f"Delay {delay} too small"
        assert delay <= base * 32 + 2, f"Delay {delay} suspiciously large"


@patch("src.engine.retry_manager.firestore")
@patch("src.engine.retry_manager.time.sleep")
def test_dlq_failure_does_not_suppress_original_exception(mock_sleep, mock_fs):
    from src.engine.retry_manager import with_retry
    mock_db = MagicMock()
    mock_fs.Client.return_value = mock_db
    mock_db.collection.side_effect = Exception("Firestore unavailable")
    @with_retry(max_retries=2, base_delay=0.001)
    def fn():
        raise RuntimeError("original error")
    with pytest.raises(RuntimeError, match="original error"):
        fn()
