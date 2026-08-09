"""
Tier 5 — Golden End-to-End Pipeline Test
Deterministic E2E test exercising complete workflow across every state transition:
NEW -> TOPIC_SELECTED -> SCRIPT_READY -> ASSETS_READY -> RENDERING -> RENDERED -> UPLOADING -> PUBLIC -> CAPTIONS_VERIFIED -> MEMORY_UPDATED -> COMPLETE
All external GCP/API calls mocked. Zero live GCP writes.
"""
import pytest
from unittest.mock import patch, MagicMock, ANY

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
def test_golden_e2e_pipeline_workflow(
    mock_upload, mock_render, mock_images, mock_voice,
    mock_metadata, mock_script, mock_fs, mock_metrics,
    mock_verifier, mock_memory
):
    mock_script.return_value = {
        "narration": "Golden test narration about enterprise security.",
        "visual_prompts": [{"text": "Server room with glowing blue nodes", "timestamp": 0}]
    }
    mock_metadata.return_value = {
        "title_suggestions": ["Zero Trust Security Principles for Boardrooms"],
        "caption": "Executive briefing on Zero Trust architecture.",
        "hashtags": ["#CyberSecurity", "#ZeroTrust", "#ExecutiveBriefing"]
    }
    mock_voice.return_value = "gs://friday-media-assets-prod/bd_threatpulse/golden_audio.mp3"
    mock_images.return_value = ["gs://friday-media-assets-prod/bd_threatpulse/golden_img1.png"]
    mock_render.return_value = (
        "gs://friday-media-assets-prod/bd_threatpulse/golden_final.mp4",
        "gs://friday-media-assets-prod/bd_threatpulse/golden_subtitles.srt"
    )
    mock_upload.return_value = "https://www.youtube.com/watch?v=golden_vid_777"

    mock_mem_instance = mock_memory.return_value
    mock_mem_instance.check_duplicate.return_value = False

    mock_ver_instance = mock_verifier.return_value
    mock_ver_instance.verify.return_value = True

    db = MagicMock()
    doc_ref = MagicMock()
    
    current_doc_state = {"status": "NEW", "retry_count": 0}
    def mock_get():
        m = MagicMock()
        m.exists = True
        m.to_dict.return_value = current_doc_state.copy()
        return m

    doc_ref.get.side_effect = mock_get

    transition_history = []
    def mock_update(data):
        if "status" in data:
            transition_history.append(data["status"])
            current_doc_state["status"] = data["status"]
        current_doc_state.update(data)

    def mock_set(data, merge=False):
        if "status" in data:
            current_doc_state["status"] = data["status"]
        current_doc_state.update(data)

    doc_ref.set.side_effect = mock_set
    doc_ref.update.side_effect = mock_update
    db.collection.return_value.document.return_value = doc_ref
    mock_fs.Client.return_value = db

    from src.engine.brand_worker import BrandWorker
    worker = BrandWorker()
    worker._generate_topic = MagicMock(return_value="Zero Trust Architecture Principles")

    worker.run_cycle("bd_threatpulse")

    expected_sequence = [
        "TOPIC_SELECTED",
        "SCRIPT_READY",
        "ASSETS_READY",
        "RENDERING",
        "RENDERED",
        "UPLOADING",
        "PUBLIC",
        "CAPTIONS_VERIFIED",
        "MEMORY_UPDATED",
        "COMPLETE"
    ]
    assert transition_history == expected_sequence, f"Transition sequence mismatch: {transition_history}"

    mock_script.assert_called_once()
    mock_metadata.assert_called_once()
    mock_voice.assert_called_once()
    mock_images.assert_called_once()
    mock_render.assert_called_once()
    mock_upload.assert_called_once()

    mock_ver_instance.verify.assert_called_once()
    assert mock_ver_instance.verify.call_args.args[2] == "bd_threatpulse"
    mock_mem_instance.add_memory.assert_called_once()
    mock_metrics.return_value.increment_metric.assert_called_with("bd_threatpulse", ANY, "published")
