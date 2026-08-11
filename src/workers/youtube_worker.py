import os
import tempfile
import logging
from google.cloud import storage, firestore
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from src.auth.youtube_auth import get_youtube_credentials

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

def parse_gcs_uri(gcs_uri: str) -> tuple[str, str]:
    """Parses a gs://bucket/path URI into (bucket_name, blob_name)."""
    if not gcs_uri.startswith("gs://"):
        raise ValueError(f"Invalid GCS URI: {gcs_uri}")
    parts = gcs_uri[5:].split("/", 1)
    if len(parts) < 2:
        raise ValueError(f"Invalid GCS URI: {gcs_uri}")
    return parts[0], parts[1]

def download_from_gcs(gcs_uri: str, local_path: str):
    """Downloads a file from Google Cloud Storage to a local path."""
    logger.info(f"Downloading GCS file {gcs_uri} to {local_path}...")
    import subprocess
    try:
        project_id = os.environ.get("GCP_PROJECT_ID", "friday-media-prod")
        res = subprocess.run(["gcloud", "storage", "cp", gcs_uri, local_path, f"--project={project_id}"], capture_output=True, text=True, check=True)
        logger.info(f"Download complete via gcloud storage.")
    except Exception as e:
        logger.warning(f"gcloud storage cp failed ({e}), falling back to Python storage client...")
        bucket_name, blob_name = parse_gcs_uri(gcs_uri)
        project_id = os.environ.get("GCP_PROJECT_ID", "friday-media-prod")
        storage_client = storage.Client(project=project_id)
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(blob_name)
        blob.download_to_filename(local_path)
        logger.info(f"Download complete via storage client.")

def upload_video(channel: str, content_id: str, video_gs_uri: str, title: str, description: str, hashtags: list[str], srt_gs_uri: str = None) -> str:
    """
    Downloads the video (and optional SRT) from GCS, uploads to YouTube (Private),
    attaches captions if SRT is provided, and updates Firestore.
    """
    logger.info(f"[{content_id}] Starting YouTube upload for channel '{channel}'...")
    
    # 1. Obtain YouTube API credentials
    creds = get_youtube_credentials(channel)
    youtube = build("youtube", "v3", credentials=creds)

    # Create temporary directory for downloads
    with tempfile.TemporaryDirectory() as tmpdir:
        local_video_path = os.path.join(tmpdir, f"{content_id}.mp4")
        
        # 2. Download video from GCS
        download_from_gcs(video_gs_uri, local_video_path)

        # 3. Format Title & Description
        safe_title = (title or f"Video Content {content_id}")[:100]
        safe_description = description or "Automated content generation."

        formatted_description = safe_description
        if hashtags:
            hashtag_str = " ".join([f"#{tag}" if not tag.startswith("#") else tag for tag in hashtags])
            formatted_description += f"\n\n{hashtag_str}"

        # 4. Upload video to YouTube (Private by default)
        logger.info(f"[{content_id}] Initiating YouTube media upload...")
        media = MediaFileUpload(
            local_video_path,
            mimetype="video/mp4",
            resumable=True
        )

        request = youtube.videos().insert(
            part="snippet,status",
            body={
                "snippet": {
                    "title": safe_title,
                    "description": formatted_description,
                    "categoryId": "28"  # Science & Technology
                },
                "status": {
                    "privacyStatus": "public"
                }
            },
            media_body=media
        )

        response = None
        while response is None:
            status, response = request.next_chunk()
            if status:
                logger.info(f"[{content_id}] Video upload progress: {int(status.progress() * 100)}%")

        video_id = response["id"]
        youtube_url = f"https://www.youtube.com/watch?v={video_id}"
        logger.info(f"[{content_id}] Video uploaded successfully. Video ID: {video_id}")

        # 5. Upload SRT captions if provided
        if srt_gs_uri:
            local_srt_path = os.path.join(tmpdir, f"{content_id}.srt")
            try:
                download_from_gcs(srt_gs_uri, local_srt_path)
                logger.info(f"[{content_id}] Initiating caption upload for video ID {video_id}...")
                
                caption_media = MediaFileUpload(
                    local_srt_path,
                    mimetype="text/plain",
                    resumable=True
                )
                
                caption_request = youtube.captions().insert(
                    part="snippet",
                    body={
                        "snippet": {
                            "videoId": video_id,
                            "language": "en",
                            "name": "English CC",
                            "isDraft": False
                        }
                    },
                    media_body=caption_media
                )
                
                caption_response = None
                while caption_response is None:
                    status, caption_response = caption_request.next_chunk()
                    if status:
                        logger.info(f"[{content_id}] Caption upload progress: {int(status.progress() * 100)}%")
                        
                logger.info(f"[{content_id}] Captions uploaded successfully.")
            except Exception as caption_err:
                logger.exception(f"[{content_id}] Caption upload failed, continuing without captions: {caption_err}")

        # 6. Update Firestore document
        logger.info(f"[{content_id}] Updating Firestore document...")
        db = firestore.Client(project=os.environ.get("GCP_PROJECT_ID", "friday-media-prod"))
        db.collection("content_items").document(content_id).update({
            "youtube_video_id": video_id,
            "youtube_url": youtube_url
        })
        logger.info(f"[{content_id}] Firestore document updated.")

        return youtube_url
