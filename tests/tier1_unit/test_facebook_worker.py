import os
import json
import urllib.error
from unittest.mock import MagicMock, patch
import pytest
from src.workers.facebook_worker import (
    upload_facebook_reel,
    check_facebook_processing_status,
    _scrub_url
)
from src.auth.facebook_auth import MetaTokenInvalidError

@pytest.fixture
def mock_urlopen():
    with patch("src.workers.facebook_worker.urllib.request.urlopen") as mock_open:
        yield mock_open

@pytest.fixture
def mock_gcs_download():
    with patch("src.workers.facebook_worker.download_from_gcs") as mock_down:
        yield mock_down

@pytest.fixture
def mock_creds():
    with patch("src.workers.facebook_worker.get_facebook_credentials") as mock_auth:
        mock_auth.return_value = "mock_page_token_xyz"
        yield mock_auth

def test_scrub_url_credential_masking():
    url = "https://graph.facebook.com/v26.0/me/accounts?access_token=EAAC123456789&limit=100"
    scrubbed = _scrub_url(url)
    assert "access_token=%5BREDACTED%5D" in scrubbed
    assert "limit=100" in scrubbed
    assert "EAAC123456789" not in scrubbed

def test_upload_facebook_reel_dry_run():
    # In dry run, none of the network paths should be triggered
    res = upload_facebook_reel(
        brand_id="wealthwise",
        page_id="1089665547569807",
        content_id="test_run_1",
        video_gs_uri="gs://bucket/video.mp4",
        title="Test Reel",
        description="Dry run verify",
        hashtags=["finance"],
        dry_run=True
    )
    assert res == "mock_fb_reel_test_run_1"

def test_upload_facebook_reel_invalid_parameters():
    # Invalid video_state
    with pytest.raises(ValueError) as exc_info:
        upload_facebook_reel(
            brand_id="wealthwise",
            page_id="1089665547569807",
            content_id="test_run_1",
            video_gs_uri="gs://bucket/video.mp4",
            title="Test",
            description="Test",
            hashtags=[],
            video_state="INVALID_STATE"
        )
    assert "Invalid video_state" in str(exc_info.value)

    # Scheduled state without scheduled_publish_time
    with pytest.raises(ValueError) as exc_info_sched:
        upload_facebook_reel(
            brand_id="wealthwise",
            page_id="1089665547569807",
            content_id="test_run_1",
            video_gs_uri="gs://bucket/video.mp4",
            title="Test",
            description="Test",
            hashtags=[],
            video_state="SCHEDULED"
        )
    assert "scheduled_publish_time required" in str(exc_info_sched.value)

def test_upload_facebook_reel_success(mock_urlopen, mock_gcs_download, mock_creds):
    # Setup GCS mock downloading behavior
    def mock_download(uri, local_path):
        with open(local_path, "wb") as f:
            f.write(b"mock_mp4_bytes")
    mock_gcs_download.side_effect = mock_download

    # Mock Graph API responses for Reels Phase 1, Phase 2, Phase 3
    # Step 1: Start response
    mock_start_resp = MagicMock()
    mock_start_resp.read.return_value = json.dumps({
        "video_id": "9876543210",
        "upload_url": "https://rupload.facebook.com/video-upload/v26.0/9876543210"
    }).encode("utf-8")

    # Step 2: Ingest response
    mock_ingest_resp = MagicMock()
    mock_ingest_resp.read.return_value = json.dumps({"success": True}).encode("utf-8")

    # Step 3: Finish response
    mock_finish_resp = MagicMock()
    mock_finish_resp.read.return_value = json.dumps({"success": True, "video_id": "9876543210"}).encode("utf-8")

    # Queue mock returns
    mock_urlopen.return_value.__enter__.side_effect = [
        mock_start_resp,
        mock_ingest_resp,
        mock_finish_resp
    ]

    video_id = upload_facebook_reel(
        brand_id="wealthwise",
        page_id="1089665547569807",
        content_id="test_run_1",
        video_gs_uri="gs://bucket/video.mp4",
        title="Valid Reel",
        description="Reels flow test",
        hashtags=["stoicism"],
        video_state="PUBLISHED"
    )

    assert video_id == "9876543210"
    assert mock_creds.call_count == 1
    assert mock_gcs_download.call_count == 1

def test_check_facebook_processing_status(mock_urlopen):
    # Success Case
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps({
        "status": {
            "video_status": "ready"
        }
    }).encode("utf-8")
    mock_urlopen.return_value.__enter__.return_value = mock_resp

    status = check_facebook_processing_status("mock_token", "9876543210")
    assert status == "ready"

def test_facebook_worker_oauth_190_error(mock_urlopen, mock_gcs_download, mock_creds):
    # Setup GCS mock downloading behavior
    def mock_download(uri, local_path):
        with open(local_path, "wb") as f:
            f.write(b"mock_bytes")
    mock_gcs_download.side_effect = mock_download

    # Mock urllib HTTPError 400 with subcode/type OAuthException
    import io
    error_payload = json.dumps({
        "error": {
            "message": "Error validating access token: Session has expired.",
            "type": "OAuthException",
            "code": 190
        }
    }).encode("utf-8")
    mock_err_response = io.BytesIO(error_payload)
    mock_err_response.code = 400
    mock_err_response.msg = "Bad Request"

    http_error = urllib.error.HTTPError(
        url="https://graph.facebook.com/v26.0/me/accounts",
        code=400,
        msg="Bad Request",
        hdrs=None,
        fp=mock_err_response
    )
    mock_urlopen.side_effect = http_error

    with pytest.raises(MetaTokenInvalidError):
        upload_facebook_reel(
            brand_id="wealthwise",
            page_id="1089665547569807",
            content_id="test_run_1",
            video_gs_uri="gs://bucket/video.mp4",
            title="Reel",
            description="Reel",
            hashtags=[],
            video_state="PUBLISHED"
        )
