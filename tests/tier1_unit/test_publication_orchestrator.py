import pytest
from unittest.mock import MagicMock, patch
from src.engine.publication_orchestrator import (
    PublicationOrchestrator,
    PublicationError
)
from src.auth.facebook_auth import MetaTokenInvalidError

@pytest.fixture
def mock_db():
    with patch("src.engine.publication_orchestrator.firestore.Client") as mock_client:
        db_instance = MagicMock()
        mock_client.return_value = db_instance
        yield db_instance

@pytest.fixture
def orchestrator(mock_db):
    return PublicationOrchestrator(db=mock_db)

@patch("src.engine.publication_orchestrator.upload_youtube_video")
@patch("src.engine.publication_orchestrator.upload_facebook_reel")
def test_publish_all_platforms_success(mock_fb_upload, mock_yt_upload, orchestrator):
    # Setup mocks
    mock_yt_upload.return_value = "https://www.youtube.com/watch?v=yt_success_123"
    mock_fb_upload.return_value = "fb_success_456"

    mock_doc_ref = MagicMock()
    orchestrator.db.collection().document.return_value = mock_doc_ref

    brand_cfg = {
        "brand_id": "wealthwise",
        "publishing_platforms": ["YouTube", "Facebook"],
        "facebook_page_id": "1089665547569807"
    }

    doc_data = {
        "final_video_uri": "gs://bucket/video.mp4",
        "srt_uri": "gs://bucket/video.srt",
        "topic": "Investment tips",
        "publishing_package": {
            "title": "Stoic Investing Guide",
            "description": "Caption guide text",
            "tags": ["finance", "stoic"]
        }
    }

    results = orchestrator.publish_content_item(
        content_id="doc_123",
        brand_cfg=brand_cfg,
        doc_data=doc_data,
        dry_run=False
    )

    assert results["youtube_video_id"] == "yt_success_123"
    assert results["facebook_reel_id"] == "fb_success_456"

    # Verify both uploaders called
    assert mock_yt_upload.call_count == 1
    assert mock_fb_upload.call_count == 1

    # Verify database updates were persisted immediately on success
    assert mock_doc_ref.update.call_count == 2
    
    # YouTube update check
    yt_call_args = mock_doc_ref.update.call_args_list[0][0][0]
    assert yt_call_args["youtube_video_id"] == "yt_success_123"
    
    # Facebook update check
    fb_call_args = mock_doc_ref.update.call_args_list[1][0][0]
    assert fb_call_args["facebook_reel_id"] == "fb_success_456"

@patch("src.engine.publication_orchestrator.upload_youtube_video")
@patch("src.engine.publication_orchestrator.upload_facebook_reel")
def test_publish_idempotency_bypasses_completed_youtube(mock_fb_upload, mock_yt_upload, orchestrator):
    mock_fb_upload.return_value = "fb_success_456"

    mock_doc_ref = MagicMock()
    orchestrator.db.collection().document.return_value = mock_doc_ref

    brand_cfg = {
        "brand_id": "wealthwise",
        "publishing_platforms": ["YouTube", "Facebook"],
        "facebook_page_id": "1089665547569807"
    }

    # YouTube already uploaded, Facebook is missing
    doc_data = {
        "final_video_uri": "gs://bucket/video.mp4",
        "youtube_video_id": "yt_already_done_111",
        "youtube_url": "https://www.youtube.com/watch?v=yt_already_done_111"
    }

    results = orchestrator.publish_content_item(
        content_id="doc_123",
        brand_cfg=brand_cfg,
        doc_data=doc_data,
        dry_run=False
    )

    assert results["youtube_video_id"] == "yt_already_done_111"
    assert results["facebook_reel_id"] == "fb_success_456"

    # Assert YouTube upload was skipped and Facebook upload ran
    assert mock_yt_upload.call_count == 0
    assert mock_fb_upload.call_count == 1
    assert mock_doc_ref.update.call_count == 1

@patch("src.engine.publication_orchestrator.upload_youtube_video")
@patch("src.engine.publication_orchestrator.upload_facebook_reel")
def test_publish_idempotency_bypasses_all_completed(mock_fb_upload, mock_yt_upload, orchestrator):
    mock_doc_ref = MagicMock()
    orchestrator.db.collection().document.return_value = mock_doc_ref

    brand_cfg = {
        "brand_id": "wealthwise",
        "publishing_platforms": ["YouTube", "Facebook"],
        "facebook_page_id": "1089665547569807"
    }

    # Both platforms completed
    doc_data = {
        "final_video_uri": "gs://bucket/video.mp4",
        "youtube_video_id": "yt_already_done_111",
        "youtube_url": "https://www.youtube.com/watch?v=yt_already_done_111",
        "facebook_reel_id": "fb_already_done_222",
        "facebook_reel_url": "https://www.facebook.com/reel/fb_already_done_222"
    }

    results = orchestrator.publish_content_item(
        content_id="doc_123",
        brand_cfg=brand_cfg,
        doc_data=doc_data,
        dry_run=False
    )

    assert results["youtube_video_id"] == "yt_already_done_111"
    assert results["facebook_reel_id"] == "fb_already_done_222"

    assert mock_yt_upload.call_count == 0
    assert mock_fb_upload.call_count == 0
    assert mock_doc_ref.update.call_count == 0

@patch("src.engine.publication_orchestrator.upload_youtube_video")
@patch("src.engine.publication_orchestrator.upload_facebook_reel")
def test_publish_failure_isolation_preserves_partial_success(mock_fb_upload, mock_yt_upload, orchestrator):
    # YouTube fails, but Facebook succeeds
    mock_yt_upload.side_effect = RuntimeError("Network timeout to Google API")
    mock_fb_upload.return_value = "fb_success_456"

    mock_doc_ref = MagicMock()
    orchestrator.db.collection().document.return_value = mock_doc_ref

    brand_cfg = {
        "brand_id": "wealthwise",
        "publishing_platforms": ["YouTube", "Facebook"],
        "facebook_page_id": "1089665547569807"
    }

    doc_data = {
        "final_video_uri": "gs://bucket/video.mp4"
    }

    with pytest.raises(PublicationError) as exc_info:
        orchestrator.publish_content_item(
            content_id="doc_123",
            brand_cfg=brand_cfg,
            doc_data=doc_data,
            dry_run=False
        )

    assert "Publishing failed for some platforms" in str(exc_info.value)
    assert "youtube: Network timeout" in str(exc_info.value)

    # Verification: Facebook was still attempted and successfully updated
    assert mock_fb_upload.call_count == 1
    assert mock_doc_ref.update.call_count == 1
    fb_call_args = mock_doc_ref.update.call_args_list[0][0][0]
    assert fb_call_args["facebook_reel_id"] == "fb_success_456"

@patch("src.engine.publication_orchestrator.upload_youtube_video")
@patch("src.engine.publication_orchestrator.upload_facebook_reel")
def test_publish_oauth_190_propagates_directly(mock_fb_upload, mock_yt_upload, orchestrator):
    # Facebook raises invalid token exception
    mock_fb_upload.side_effect = MetaTokenInvalidError("Meta token is revoked.")

    mock_doc_ref = MagicMock()
    orchestrator.db.collection().document.return_value = mock_doc_ref

    brand_cfg = {
        "brand_id": "wealthwise",
        "publishing_platforms": ["Facebook"],
        "facebook_page_id": "1089665547569807"
    }

    doc_data = {
        "final_video_uri": "gs://bucket/video.mp4"
    }

    # MetaTokenInvalidError should bubble out directly without being masked in PublicationError
    with pytest.raises(MetaTokenInvalidError) as exc_info:
        orchestrator.publish_content_item(
            content_id="doc_123",
            brand_cfg=brand_cfg,
            doc_data=doc_data,
            dry_run=False
        )

    assert "Meta token is revoked." in str(exc_info.value)
    assert mock_doc_ref.update.call_count == 0


@patch("src.engine.publication_orchestrator.upload_youtube_video")
@patch("src.engine.publication_orchestrator.upload_facebook_reel")
def test_orchestrator_retry_idempotency_flow(mock_fb_upload, mock_yt_upload, orchestrator):
    # --- Execution 1: YouTube SUCCESS, Facebook FAILURE ---
    mock_yt_upload.return_value = "https://www.youtube.com/watch?v=yt_vid_success"
    mock_fb_upload.side_effect = RuntimeError("Meta API Timeout")

    mock_doc_ref = MagicMock()
    orchestrator.db.collection().document.return_value = mock_doc_ref

    brand_cfg = {
        "brand_id": "wealthwise",
        "publishing_platforms": ["YouTube", "Facebook"],
        "facebook_page_id": "1089665547569807"
    }

    doc_data_1 = {
        "final_video_uri": "gs://bucket/video.mp4"
    }

    with pytest.raises(PublicationError) as exc_info:
        orchestrator.publish_content_item(
            content_id="doc_123",
            brand_cfg=brand_cfg,
            doc_data=doc_data_1,
            dry_run=False
        )
    
    assert "Publishing failed for some platforms" in str(exc_info.value)
    assert "facebook: Meta API Timeout" in str(exc_info.value)

    # Verify uploaders called during Execution 1
    assert mock_yt_upload.call_count == 1
    assert mock_fb_upload.call_count == 1

    # Verify YouTube got persisted immediately, but Facebook did not
    assert mock_doc_ref.update.call_count == 1
    yt_call_args = mock_doc_ref.update.call_args_list[0][0][0]
    assert yt_call_args["youtube_video_id"] == "yt_vid_success"

    # --- Execution 2: Retry (YouTube SKIPPED, Facebook SUCCESS) ---
    # Setup Facebook to succeed on this retry run
    mock_fb_upload.side_effect = None
    mock_fb_upload.return_value = "fb_reel_success"

    # Simulate updated doc data (obtained from firestore on retry)
    doc_data_2 = {
        "final_video_uri": "gs://bucket/video.mp4",
        "youtube_video_id": "yt_vid_success",
        "youtube_url": "https://www.youtube.com/watch?v=yt_vid_success"
    }

    results = orchestrator.publish_content_item(
        content_id="doc_123",
        brand_cfg=brand_cfg,
        doc_data=doc_data_2,
        dry_run=False
    )

    # Assert final result mapping
    assert results["youtube_video_id"] == "yt_vid_success"
    assert results["facebook_reel_id"] == "fb_reel_success"

    # Verify call counts across both executions
    # YouTube should be called exactly ONCE (Execution 1: 1, Execution 2: 0)
    # Facebook should be called twice (Execution 1: 1, Execution 2: 1)
    assert mock_yt_upload.call_count == 1
    assert mock_fb_upload.call_count == 2

