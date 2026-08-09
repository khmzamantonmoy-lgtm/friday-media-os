"""
Tier 2 — Integration: Brand Worker
All external calls mocked. Verifies state transitions and failure handling.
"""
import pytest
from unittest.mock import patch, MagicMock, call
from src.engine.state_machine import ContentState

def _setup_happy_path_mocks():
    mocks = {}
    mocks["generate_script"] = MagicMock(return_value={
        "narration": "Test narration",
        "visual_prompts": [{"text": "Scene 1", "timestamp": 0}]
    })
    mocks["generate_metadata"] = MagicMock(return_value={
        "title_suggestions": ["Test Title"],
        "caption": "Test caption",
        "hashtags": ["#test"]
    })
    mocks["synthesize_voice"] = MagicMock(return_value="gs://bucket/audio.mp3")
    mocks["generate_images"] = MagicMock(return_value=["gs://bucket/img1.png"])
    mocks["render_video"] = MagicMock(return_value=("gs://bucket/video.mp4", "gs://bucket/subs.srt"))
    mocks["upload_video"] = MagicMock(return_value="https://youtube.com/watch?v=test123")
    return mocks

def _make_mock_doc_ref(initial_status="NEW", initial_retry=0):
    doc_ref = MagicMock()
    doc_state = {"status": initial_status, "topic": "Test topic", "retry_count": initial_retry}
    
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

@patch("src.engine.brand_worker.SemanticMemory")
@patch("src.engine.brand_worker.PublicationVerifier")
@patch("src.engine.brand_worker.MetricsService")
@patch("src.engine.brand_worker.firestore")
@patch("src.engine.brand_worker.generate_script")
@patch("src.engine.brand_worker.generate_metadata")
@patch("src.engine.brand_worker.synthesize_voice")
@patch("src.engine.brand_worker.generate_images")
@patch("src.engine.brand_worker.render_video")
@patch("src.engine.brand_worker.upload_video")
def test_full_cycle_writes_complete(
    mock_upload, mock_render, mock_images, mock_voice,
    mock_metadata, mock_script, mock_fs, mock_metrics,
    mock_verifier, mock_memory
):
    happy = _setup_happy_path_mocks()
    mock_script.return_value = happy["generate_script"].return_value
    mock_metadata.return_value = happy["generate_metadata"].return_value
    mock_voice.return_value = happy["synthesize_voice"].return_value
    mock_images.return_value = happy["generate_images"].return_value
    mock_render.return_value = happy["render_video"].return_value
    mock_upload.return_value = happy["upload_video"].return_value

    mock_memory.return_value.check_duplicate.return_value = False
    mock_verifier.return_value.verify.return_value = True
    mock_verifier.return_value.verify_status.return_value = "VERIFIED"

    doc_ref, doc_state = _make_mock_doc_ref()
    db = MagicMock()
    db.collection.return_value.document.return_value = doc_ref
    mock_fs.Client.return_value = db

    from src.engine.brand_worker import BrandWorker
    worker = BrandWorker()
    worker._generate_topic = MagicMock(return_value="Test topic")
    worker.run_cycle("bd_threatpulse")

    update_calls = [str(c) for c in doc_ref.update.call_args_list]
    assert any("COMPLETE" in c for c in update_calls), f"Expected COMPLETE in updates: {update_calls}"

@patch("src.engine.brand_worker.SemanticMemory")
@patch("src.engine.brand_worker.PublicationVerifier")
@patch("src.engine.brand_worker.MetricsService")
@patch("src.engine.brand_worker.firestore")
def test_duplicate_topic_aborts_cycle(mock_fs, mock_metrics, mock_verifier, mock_memory):
    mock_memory.return_value.check_duplicate.return_value = True
    db = MagicMock()
    mock_fs.Client.return_value = db
    from src.engine.brand_worker import BrandWorker
    worker = BrandWorker()
    worker._generate_topic = MagicMock(return_value=None)
    worker.run_cycle("bd_threatpulse")
    db.collection.return_value.document.return_value.set.assert_not_called()

@patch("src.engine.brand_worker.SemanticMemory")
@patch("src.engine.brand_worker.PublicationVerifier")
@patch("src.engine.brand_worker.MetricsService")
@patch("src.engine.brand_worker.firestore")
def test_content_id_has_brand_prefix(mock_fs, mock_metrics, mock_verifier, mock_memory):
    import inspect
    import src.engine.brand_worker as bw_module
    src_code = inspect.getsource(bw_module.BrandWorker.run_cycle)
    assert "{brand_id}_" in src_code, "content_id must be prefixed with brand_id"

@patch("src.engine.retry_manager.time.sleep")
@patch("src.engine.brand_worker.SemanticMemory")
@patch("src.engine.brand_worker.PublicationVerifier")
@patch("src.engine.brand_worker.MetricsService")
@patch("src.engine.brand_worker.firestore")
@patch("src.engine.brand_worker.generate_script")
@patch("src.engine.brand_worker.generate_metadata")
@patch("src.engine.brand_worker.synthesize_voice")
@patch("src.engine.brand_worker.generate_images")
@patch("src.engine.brand_worker.render_video")
@patch("src.engine.brand_worker.upload_video")
def test_upload_failure_triggers_retry(
    mock_upload, mock_render, mock_images, mock_voice,
    mock_metadata, mock_script, mock_fs, mock_metrics,
    mock_verifier, mock_memory, mock_sleep
):
    happy = _setup_happy_path_mocks()
    mock_script.return_value = happy["generate_script"].return_value
    mock_metadata.return_value = happy["generate_metadata"].return_value
    mock_voice.return_value = happy["synthesize_voice"].return_value
    mock_images.return_value = happy["generate_images"].return_value
    mock_render.return_value = happy["render_video"].return_value
    mock_upload.side_effect = Exception("Upload failed: 503")
    mock_memory.return_value.check_duplicate.return_value = False

    doc_ref, doc_state = _make_mock_doc_ref()
    db = MagicMock()
    db.collection.return_value.document.return_value = doc_ref
    mock_fs.Client.return_value = db

    from src.engine.brand_worker import BrandWorker
    worker = BrandWorker()
    worker._generate_topic = MagicMock(return_value="Test topic")
    worker.run_cycle("bd_threatpulse")

    update_calls = [str(c) for c in doc_ref.update.call_args_list]
    assert any("RETRY" in c or "FAILED" in c for c in update_calls), f"Expected RETRY or FAILED: {update_calls}"

@patch("src.engine.retry_manager.time.sleep")
@patch("src.engine.brand_worker.SemanticMemory")
@patch("src.engine.brand_worker.PublicationVerifier")
@patch("src.engine.brand_worker.MetricsService")
@patch("src.engine.brand_worker.firestore")
def test_max_retries_sends_to_dlq(mock_fs, mock_metrics, mock_verifier, mock_memory, mock_sleep):
    mock_memory.return_value.check_duplicate.return_value = False
    doc_ref = MagicMock()
    doc_ref.id = "test_item_999"
    db = MagicMock()
    db.collection.return_value.document.return_value = doc_ref
    mock_fs.Client.return_value = db
    mock_fs.SERVER_TIMESTAMP = "ts"

    from src.engine.brand_worker import BrandWorker
    worker = BrandWorker()
    # Invoke _handle_failure with retry_count=5
    worker._handle_failure(
        doc_ref=doc_ref,
        data={"retry_count": 5},
        state=ContentState.RENDERING,
        error_msg="Render timeout",
        brand_id="bd_threatpulse",
        today_iso="2026-08-07"
    )

    update_calls = [str(c) for c in doc_ref.update.call_args_list]
    assert any("FAILED" in c for c in update_calls), f"Expected FAILED: {update_calls}"
    dlq_calls = str(db.collection.call_args_list)
    assert "dead_letter_queue" in dlq_calls or db.collection.return_value.add.called
