"""
Tier 2 — Integration: Publication Verifier
YouTube API and Firestore fully mocked.
"""
import pytest
from unittest.mock import patch, MagicMock


def _make_youtube_mock(privacy="public", upload_status="processed",
                       has_captions=True, thumbnail_keys=("default", "medium", "high")):
    yt = MagicMock()
    video_item = {
        "status": {"privacyStatus": privacy, "uploadStatus": upload_status},
        "snippet": {"thumbnails": {k: {} for k in thumbnail_keys}},
    }
    yt.videos.return_value.list.return_value.execute.return_value = {"items": [video_item]}
    captions = [{"snippet": {}}] if has_captions else []
    yt.captions.return_value.list.return_value.execute.return_value = {"items": captions}
    return yt


@patch("src.engine.publication_verifier.firestore")
@patch("src.engine.publication_verifier.build")
@patch("src.engine.publication_verifier.get_youtube_credentials")
def test_passes_when_public_processed_captioned(mock_creds, mock_build, mock_fs):
    mock_build.return_value = _make_youtube_mock()
    mock_db = MagicMock()
    mock_fs.Client.return_value = mock_db
    from src.engine.publication_verifier import PublicationVerifier
    v = PublicationVerifier()
    result = v.verify("doc_001", "abc123", "bd_threatpulse")
    assert result is True
    mock_db.collection().document().update.assert_called_once()
    update_data = mock_db.collection().document().update.call_args.args[0]
    assert update_data.get("youtube_verified") is True


@patch("src.engine.publication_verifier.firestore")
@patch("src.engine.publication_verifier.build")
@patch("src.engine.publication_verifier.get_youtube_credentials")
def test_fails_when_private(mock_creds, mock_build, mock_fs):
    mock_build.return_value = _make_youtube_mock(privacy="private")
    mock_fs.Client.return_value = MagicMock()
    from src.engine.publication_verifier import PublicationVerifier
    v = PublicationVerifier()
    assert v.verify("doc_001", "abc123", "bd_threatpulse") is False


@patch("src.engine.publication_verifier.firestore")
@patch("src.engine.publication_verifier.build")
@patch("src.engine.publication_verifier.get_youtube_credentials")
def test_fails_when_not_processed(mock_creds, mock_build, mock_fs):
    mock_build.return_value = _make_youtube_mock(upload_status="uploaded")
    mock_fs.Client.return_value = MagicMock()
    from src.engine.publication_verifier import PublicationVerifier
    v = PublicationVerifier()
    assert v.verify("doc_001", "abc123", "bd_threatpulse") is False


@patch("src.engine.publication_verifier.firestore")
@patch("src.engine.publication_verifier.build")
@patch("src.engine.publication_verifier.get_youtube_credentials")
def test_fails_when_no_captions(mock_creds, mock_build, mock_fs):
    mock_build.return_value = _make_youtube_mock(has_captions=False)
    mock_fs.Client.return_value = MagicMock()
    from src.engine.publication_verifier import PublicationVerifier
    v = PublicationVerifier()
    assert v.verify("doc_001", "abc123", "bd_threatpulse") is False


@patch("src.engine.publication_verifier.firestore")
@patch("src.engine.publication_verifier.build")
@patch("src.engine.publication_verifier.get_youtube_credentials")
def test_fails_when_only_default_thumbnail(mock_creds, mock_build, mock_fs):
    mock_build.return_value = _make_youtube_mock(thumbnail_keys=("default",))
    mock_fs.Client.return_value = MagicMock()
    from src.engine.publication_verifier import PublicationVerifier
    v = PublicationVerifier()
    assert v.verify("doc_001", "abc123", "bd_threatpulse") is False


@patch("src.engine.publication_verifier.firestore")
@patch("src.engine.publication_verifier.build")
@patch("src.engine.publication_verifier.get_youtube_credentials")
def test_firestore_youtube_verified_written_on_pass(mock_creds, mock_build, mock_fs):
    mock_build.return_value = _make_youtube_mock()
    mock_db = MagicMock()
    mock_fs.Client.return_value = mock_db
    from src.engine.publication_verifier import PublicationVerifier
    v = PublicationVerifier()
    v.verify("doc_999", "xyz789", "wealthwise")
    update_calls = mock_db.collection().document().update.call_args_list
    assert len(update_calls) == 1
    data = update_calls[0].args[0]
    assert data["youtube_verified"] is True
    assert "verified_at" in data


@patch("src.engine.publication_verifier.firestore")
@patch("src.engine.publication_verifier.build")
@patch("src.engine.publication_verifier.get_youtube_credentials")
def test_brand_scoped_credentials_used(mock_creds, mock_build, mock_fs):
    mock_build.return_value = _make_youtube_mock()
    mock_fs.Client.return_value = MagicMock()
    from src.engine.publication_verifier import PublicationVerifier
    v = PublicationVerifier()
    v.verify("doc_001", "abc123", "kids_universe")
    mock_creds.assert_called_with("kids_universe")


@patch("src.engine.publication_verifier.firestore")
@patch("src.engine.publication_verifier.build")
@patch("src.engine.publication_verifier.get_youtube_credentials")
def test_missing_video_returns_false(mock_creds, mock_build, mock_fs):
    yt = MagicMock()
    yt.videos.return_value.list.return_value.execute.return_value = {"items": []}
    mock_build.return_value = yt
    mock_fs.Client.return_value = MagicMock()
    from src.engine.publication_verifier import PublicationVerifier
    v = PublicationVerifier()
    assert v.verify("doc_001", "nonexistent", "bd_threatpulse") is False


@patch("src.engine.publication_verifier.firestore")
@patch("src.engine.publication_verifier.build")
@patch("src.engine.publication_verifier.get_youtube_credentials")
def test_youtube_api_exception_returns_false(mock_creds, mock_build, mock_fs):
    yt = MagicMock()
    yt.videos.return_value.list.return_value.execute.side_effect = Exception("API error")
    mock_build.return_value = yt
    mock_fs.Client.return_value = MagicMock()
    from src.engine.publication_verifier import PublicationVerifier
    v = PublicationVerifier()
    result = v.verify("doc_001", "abc123", "bd_threatpulse")
    assert result is False
