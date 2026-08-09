"""
Tier 4 — Chaos: Worker Crash Scenarios at Each Pipeline Stage
Verifies correct RETRY/FAILED state after crash at any stage.
All mocked.
"""
import pytest
from unittest.mock import patch, MagicMock
from src.engine.state_machine import ContentState

def _make_mock_doc_ref(initial_status="NEW", initial_retry=0):
    doc_ref = MagicMock()
    doc_state = {"status": initial_status, "topic": "test topic", "retry_count": initial_retry}
    def mock_get():
        m = MagicMock()
        m.exists = True
        m.to_dict.return_value = doc_state.copy()
        return m
    doc_ref.get.side_effect = mock_get
    def mock_set(data, merge=False):
        doc_state.update(data)
    def mock_update(data):
        doc_state.update(data)
    doc_ref.set.side_effect = mock_set
    doc_ref.update.side_effect = mock_update
    return doc_ref, doc_state

def _run_cycle_with_crash_at(crash_worker_path, brand_id="bd_threatpulse"):
    with patch("src.engine.retry_manager.time.sleep"), \
         patch("src.engine.brand_worker.SemanticMemory") as MockMem, \
         patch("src.engine.brand_worker.PublicationVerifier") as MockVerifier, \
         patch("src.engine.brand_worker.MetricsService"), \
         patch("src.engine.brand_worker.firestore") as mock_fs, \
         patch("src.engine.brand_worker.generate_script") as mock_script, \
         patch("src.engine.brand_worker.generate_metadata") as mock_meta, \
         patch("src.engine.brand_worker.synthesize_voice") as mock_voice, \
         patch("src.engine.brand_worker.generate_images") as mock_images, \
         patch("src.engine.brand_worker.render_video") as mock_render, \
         patch("src.engine.brand_worker.upload_video") as mock_upload:

        MockMem.return_value.check_duplicate.return_value = False
        mock_script.return_value = {"narration": "test", "visual_prompts": []}
        mock_meta.return_value = {"title_suggestions": ["T"], "caption": "", "hashtags": []}
        mock_voice.return_value = "gs://audio"
        mock_images.return_value = ["gs://img"]
        mock_render.return_value = ("gs://video", "gs://srt")
        mock_upload.return_value = "https://youtube.com/watch?v=abc"
        MockVerifier.return_value.verify.return_value = True

        if crash_worker_path == "script":
            mock_script.side_effect = Exception("Script crash")
        elif crash_worker_path == "voice":
            mock_voice.side_effect = Exception("Voice crash")
        elif crash_worker_path == "images":
            mock_images.side_effect = Exception("Images crash")
        elif crash_worker_path == "render":
            mock_render.side_effect = Exception("Render crash")
        elif crash_worker_path == "upload":
            mock_upload.side_effect = Exception("Upload crash")

        doc_ref, doc_state = _make_mock_doc_ref()
        db = MagicMock()
        db.collection.return_value.document.return_value = doc_ref
        mock_fs.Client.return_value = db
        mock_fs.SERVER_TIMESTAMP = "ts"

        from src.engine.brand_worker import BrandWorker
        worker = BrandWorker()
        worker._generate_topic = MagicMock(return_value="test topic")
        worker.run_cycle(brand_id)

        return [str(c) for c in doc_ref.update.call_args_list]

def _assert_retry_or_failed(update_calls, crash_stage):
    has_failure = any("RETRY" in c or "FAILED" in c for c in update_calls)
    assert has_failure, f"Expected RETRY or FAILED after {crash_stage} crash. Got: {update_calls}"

def test_crash_during_script_generation():
    calls = _run_cycle_with_crash_at("script")
    _assert_retry_or_failed(calls, "script")

def test_crash_during_voice_synthesis():
    calls = _run_cycle_with_crash_at("voice")
    _assert_retry_or_failed(calls, "voice")

def test_crash_during_image_generation():
    calls = _run_cycle_with_crash_at("images")
    _assert_retry_or_failed(calls, "images")

def test_crash_during_render():
    calls = _run_cycle_with_crash_at("render")
    _assert_retry_or_failed(calls, "render")

def test_crash_during_upload():
    calls = _run_cycle_with_crash_at("upload")
    _assert_retry_or_failed(calls, "upload")

@patch("src.engine.retry_manager.time.sleep")
@patch("src.engine.brand_worker.SemanticMemory")
@patch("src.engine.brand_worker.PublicationVerifier")
@patch("src.engine.brand_worker.MetricsService")
@patch("src.engine.brand_worker.firestore")
def test_crash_at_max_retries_sends_to_dlq(mock_fs, mock_metrics, mock_verifier, mock_memory, mock_sleep):
    mock_memory.return_value.check_duplicate.return_value = False
    doc_ref = MagicMock()
    doc_ref.id = "test_item_max_retries"
    db = MagicMock()
    db.collection.return_value.document.return_value = doc_ref
    mock_fs.Client.return_value = db
    mock_fs.SERVER_TIMESTAMP = "ts"
    from src.engine.brand_worker import BrandWorker
    worker = BrandWorker()
    worker._handle_failure(
        doc_ref=doc_ref,
        data={"retry_count": 5},
        state=ContentState.RENDERING,
        error_msg="Max retries reached",
        brand_id="bd_threatpulse",
        today_iso="2026-08-07"
    )
    update_calls = [str(c) for c in doc_ref.update.call_args_list]
    assert any("FAILED" in c for c in update_calls), f"Expected FAILED: {update_calls}"
    dlq_calls = str(db.collection.call_args_list)
    assert "dead_letter_queue" in dlq_calls or db.collection.return_value.add.called
