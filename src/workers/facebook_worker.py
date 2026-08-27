import os
# NOTE: facebook_worker.py was minimally extended to expose START and UPLOAD+FINISH
# as separate callables. This is required by the META-15A Point 0 idempotency design
# (persist video_id between START and binary upload). The original upload_facebook_reel
# function is preserved byte-for-byte for backward compatibility.
import json
import logging
import tempfile
import urllib.request
import urllib.parse
from src.auth.facebook_auth import get_facebook_credentials, MetaTokenInvalidError
from src.workers.youtube_worker import download_from_gcs

logger = logging.getLogger(__name__)

def _scrub_url(url: str) -> str:
    """Removes query parameter credentials from logging outputs."""
    parsed = urllib.parse.urlparse(url)
    query_params = urllib.parse.parse_qsl(parsed.query)
    scrubbed_query = []
    for k, v in query_params:
        if k == "access_token":
            scrubbed_query.append((k, "[REDACTED]"))
        else:
            scrubbed_query.append((k, v))
    return urllib.parse.urlunparse((
        parsed.scheme,
        parsed.netloc,
        parsed.path,
        parsed.params,
        urllib.parse.urlencode(scrubbed_query),
        parsed.fragment
    ))

def _handle_http_error(code: int, body: str):
    """Processes Meta error payloads to parse invalid token statuses."""
    try:
        err_json = json.loads(body)
        error_details = err_json.get("error", {})
        err_code = error_details.get("code")
        err_subcode = error_details.get("error_subcode")
        err_type = error_details.get("type")
        err_msg = error_details.get("message", body)
        
        if err_code == 190 or err_type == "OAuthException":
            raise MetaTokenInvalidError(
                f"Meta OAuth token invalid or expired (code={err_code}, subcode={err_subcode}): {err_msg}"
            )
        raise RuntimeError(f"Meta Graph API HTTP {code} Error (code={err_code}): {err_msg}")
    except json.JSONDecodeError:
        raise RuntimeError(f"Meta Graph API HTTP {code} Error: {body}")

def _make_graph_request(url: str, params: dict = None, method: str = "GET", data: bytes = None, extra_headers: dict = None) -> dict:
    """Helper to perform HTTP Graph API requests and mask credentials."""
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    
    req = urllib.request.Request(url, method=method, data=data)
    if extra_headers:
        for k, v in extra_headers.items():
            req.add_header(k, v)

    scrubbed_url = _scrub_url(url)
    logger.info(f"Executing {method} request to {scrubbed_url}")
    
    try:
        with urllib.request.urlopen(req) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8")
        _handle_http_error(e.code, error_body)

def check_facebook_processing_status(page_token: str, video_id: str) -> str:
    """
    Queries Graph API GET /v26.0/{video_id}?fields=status to check processing state.
    Returns: 'ready', 'processing', or 'failed'.
    """
    url = f"https://graph.facebook.com/v26.0/{video_id}"
    try:
        response_data = _make_graph_request(url, {
            "fields": "status",
            "access_token": page_token
        })
        status_info = response_data.get("status", {})
        video_status = status_info.get("video_status")
        logger.info(f"Video {video_id} status on Meta: {video_status}")
        return video_status
    except Exception as e:
        logger.error(f"Failed to check processing status for video {video_id}: {e}")
        return "failed"

def upload_facebook_reel(
    brand_id: str,
    page_id: str,
    content_id: str,
    video_gs_uri: str,
    title: str,
    description: str,
    hashtags: list[str],
    video_state: str = "PUBLISHED",
    scheduled_publish_time: int = None,
    dry_run: bool = False
) -> str:
    """
    Executes Meta Reels start -> upload -> finish ingestion sequence.
    Handles credential resolution in-memory and keeps outputs clean of tokens.
    """
    if video_state not in ["PUBLISHED", "DRAFT", "SCHEDULED"]:
        raise ValueError(f"Invalid video_state: {video_state}")
        
    if video_state == "SCHEDULED" and not scheduled_publish_time:
        raise ValueError("scheduled_publish_time required when video_state is SCHEDULED")

    if dry_run:
        logger.info(f"[DRY_RUN] Simulating Facebook Reel upload for {brand_id} to Page {page_id}")
        logger.info(f"[DRY_RUN] Video GCS: {video_gs_uri}, State: {video_state}")
        return f"mock_fb_reel_{content_id}"

    # 1. Fetch credentials dynamically in-memory
    page_token = get_facebook_credentials(brand_id, page_id)

    # Prepare formatted description
    safe_description = description or ""
    if hashtags:
        hashtag_str = " ".join([f"#{tag}" if not tag.startswith("#") else tag for tag in hashtags])
        safe_description += f"\n\n{hashtag_str}"

    with tempfile.TemporaryDirectory() as tmpdir:
        local_video_path = os.path.join(tmpdir, f"{content_id}.mp4")
        
        # 2. Download vertical MP4 from GCS
        download_from_gcs(video_gs_uri, local_video_path)
        file_size = os.path.getsize(local_video_path)

        # 3. Phase 1: Initialize upload
        init_url = f"https://graph.facebook.com/v26.0/{page_id}/video_reels"
        init_data = _make_graph_request(init_url, {
            "upload_phase": "start",
            "access_token": page_token
        }, method="POST")

        video_id = init_data.get("video_id")
        upload_url = init_data.get("upload_url")
        if not video_id or not upload_url:
            raise RuntimeError("Initialization response missing video_id or upload_url")

        # 4. Phase 2: Binary Video Chunk Upload
        with open(local_video_path, "rb") as f:
            video_bytes = f.read()

        logger.info(f"Uploading {file_size} bytes to Meta upload server...")
        _make_graph_request(upload_url, method="POST", data=video_bytes, extra_headers={
            "Authorization": f"OAuth {page_token}",
            "offset": "0",
            "file_size": str(file_size),
            "Content-Type": "application/octet-stream"
        })

        # 5. Phase 3: Finalize and Publish Ingestion
        finish_url = f"https://graph.facebook.com/v26.0/{page_id}/video_reels"
        finish_params = {
            "upload_phase": "finish",
            "video_id": video_id,
            "video_state": video_state,
            "access_token": page_token,
            "description": safe_description
        }
        if video_state == "SCHEDULED" and scheduled_publish_time:
            finish_params["scheduled_publish_time"] = str(scheduled_publish_time)

        _make_graph_request(finish_url, params=finish_params, method="POST")
        logger.info(f"Reel successfully finalized on Meta Page {page_id}. Video ID: {video_id}")
        return video_id


# ---------------------------------------------------------------------------
# Phase-split API required by PublicationOrchestrator for META-15A idempotency
# ---------------------------------------------------------------------------

def facebook_reel_start(brand_id: str, page_id: str) -> tuple:
    """
    Phase 1 only: Initialise a Reels upload session.

    Returns a 3-tuple ``(video_id, upload_url, page_token)`` — all values
    remain in-memory only and must never be logged or persisted as
    credentials. The caller is responsible for persisting ``video_id``
    (Point 0) to Firestore before calling :func:`facebook_reel_upload_and_finish`.
    """
    page_token = get_facebook_credentials(brand_id, page_id)
    init_url = f"https://graph.facebook.com/v26.0/{page_id}/video_reels"
    init_data = _make_graph_request(
        init_url,
        {"upload_phase": "start", "access_token": page_token},
        method="POST",
    )
    video_id = init_data.get("video_id")
    upload_url = init_data.get("upload_url")
    if not video_id or not upload_url:
        raise RuntimeError("START response missing video_id or upload_url")
    logger.info(f"Facebook Reel session started for Page {page_id}. video_id={video_id}")
    return video_id, upload_url, page_token


def facebook_reel_upload_and_finish(
    page_id: str,
    page_token: str,
    video_id: str,
    upload_url: str,
    content_id: str,
    video_gs_uri: str,
    video_state: str,
    description: str,
    scheduled_publish_time: int = None,
) -> str:
    """
    Phases 2 + 3: Binary upload followed by FINISH.

    ``page_token`` is passed in-memory from :func:`facebook_reel_start`;
    it is never logged. Returns ``video_id`` on success.
    """
    if video_state not in ["PUBLISHED", "DRAFT", "SCHEDULED"]:
        raise ValueError(f"Invalid video_state: {video_state}")
    if video_state == "SCHEDULED" and not scheduled_publish_time:
        raise ValueError("scheduled_publish_time required when video_state is SCHEDULED")

    with tempfile.TemporaryDirectory() as tmpdir:
        local_video_path = os.path.join(tmpdir, f"{content_id}.mp4")
        download_from_gcs(video_gs_uri, local_video_path)
        file_size = os.path.getsize(local_video_path)

        with open(local_video_path, "rb") as f:
            video_bytes = f.read()

        logger.info(f"[{content_id}] Uploading {file_size} bytes to Meta upload server...")
        _make_graph_request(
            upload_url,
            method="POST",
            data=video_bytes,
            extra_headers={
                "Authorization": f"OAuth {page_token}",
                "offset": "0",
                "file_size": str(file_size),
                "Content-Type": "application/octet-stream",
            },
        )

        finish_url = f"https://graph.facebook.com/v26.0/{page_id}/video_reels"
        finish_params = {
            "upload_phase": "finish",
            "video_id": video_id,
            "video_state": video_state,
            "access_token": page_token,
            "description": description,
        }
        if video_state == "SCHEDULED" and scheduled_publish_time:
            finish_params["scheduled_publish_time"] = str(scheduled_publish_time)

        _make_graph_request(finish_url, params=finish_params, method="POST")
        logger.info(
            f"[{content_id}] Reel finalised on Meta Page {page_id}. video_id={video_id}"
        )
        return video_id
