"""
Tier 1 — Unit: Publication Verifier Race Condition
Zero GCP. Pure logic with mocks.
"""
import pytest
from unittest.mock import MagicMock, patch
from src.engine.publication_verifier import PublicationVerifier

@pytest.fixture
def verifier():
    with patch("src.engine.publication_verifier.firestore.Client"):
        pv = PublicationVerifier()
        pv.db = MagicMock()
        return pv

def test_uploaded_processing_pending(verifier):
    """Scenario A: uploadStatus='uploaded' (processing pending) -> returns PENDING, not FAILED."""
    mock_youtube = MagicMock()
    verifier._youtube_clients["bd_threatpulse"] = mock_youtube
    
    mock_youtube.videos().list().execute.return_value = {
        "items": [{
            "status": {
                "privacyStatus": "public",
                "uploadStatus": "uploaded"
            },
            "snippet": {
                "thumbnails": {"default": {}, "high": {}}
            }
        }]
    }

    result = verifier.verify_status("doc_123", "yt_vid_123", "bd_threatpulse")
    assert result == "PENDING"
    assert verifier.verify("doc_123", "yt_vid_123", "bd_threatpulse") is False

def test_processed_and_public_verification_success(verifier):
    """Scenario B & E: processed + public + thumbnail + captions -> returns VERIFIED and updates Firestore."""
    mock_youtube = MagicMock()
    verifier._youtube_clients["bd_threatpulse"] = mock_youtube

    mock_youtube.videos().list().execute.return_value = {
        "items": [{
            "status": {
                "privacyStatus": "public",
                "uploadStatus": "processed"
            },
            "snippet": {
                "thumbnails": {"default": {}, "high": {}}
            }
        }]
    }

    mock_youtube.captions().list().execute.return_value = {
        "items": [{"id": "cap_1"}]
    }

    mock_doc_ref = MagicMock()
    verifier.db.collection().document.return_value = mock_doc_ref

    result = verifier.verify_status("doc_123", "yt_vid_123", "bd_threatpulse")
    assert result == "VERIFIED"
    assert verifier.verify("doc_123", "yt_vid_123", "bd_threatpulse") is True
    assert mock_doc_ref.update.call_count == 2
    assert mock_doc_ref.update.call_args[0][0]["youtube_verified"] is True

def test_processed_and_non_public(verifier):
    """Scenario C: processed but privacyStatus != 'public' -> returns FAILED."""
    mock_youtube = MagicMock()
    verifier._youtube_clients["bd_threatpulse"] = mock_youtube

    mock_youtube.videos().list().execute.return_value = {
        "items": [{
            "status": {
                "privacyStatus": "private",
                "uploadStatus": "processed"
            },
            "snippet": {
                "thumbnails": {"default": {}, "high": {}}
            }
        }]
    }

    result = verifier.verify_status("doc_123", "yt_vid_123", "bd_threatpulse")
    assert result == "FAILED"

def test_upload_failure(verifier):
    """Scenario D: video not found / API failure -> returns FAILED."""
    mock_youtube = MagicMock()
    verifier._youtube_clients["bd_threatpulse"] = mock_youtube

    mock_youtube.videos().list().execute.return_value = {"items": []}

    result = verifier.verify_status("doc_123", "yt_vid_123", "bd_threatpulse")
    assert result == "FAILED"
