import logging
from googleapiclient.discovery import build
from google.cloud import firestore
import datetime
from src.auth.youtube_auth import get_youtube_credentials

logger = logging.getLogger(__name__)

class PublicationVerifier:
    def __init__(self):
        self.db = firestore.Client()
        self._youtube_clients: dict = {}

    def _get_youtube_client(self, brand_id: str):
        """Returns a brand-scoped YouTube API client, cached per brand."""
        if brand_id not in self._youtube_clients:
            creds = get_youtube_credentials(brand_id)
            self._youtube_clients[brand_id] = build(
                "youtube", "v3", credentials=creds, cache_discovery=False
            )
        return self._youtube_clients[brand_id]

    def verify_status(self, doc_id: str, video_id: str, brand_id: str = "bd_threatpulse") -> str:
        """
        Verify YouTube video processing and publication status.
        Returns:
            "VERIFIED": Processed, public, custom thumbnail and captions present.
            "PENDING": Video uploaded and public, but YouTube processing is pending.
            "FAILED": Video missing, private, or rejected.
        """
        try:
            youtube = self._get_youtube_client(brand_id)
            
            # Check video status
            video_response = youtube.videos().list(
                part="status,processingDetails,snippet",
                id=video_id
            ).execute()

            if not video_response.get("items"):
                logger.error(f"Video {video_id} not found.")
                return "FAILED"
            
            video = video_response["items"][0]
            status = video.get("status", {})
            privacy_status = status.get("privacyStatus")
            upload_status = status.get("uploadStatus")

            if privacy_status != "public":
                logger.warning(f"Video {video_id} is not public (status: {privacy_status})")
                return "FAILED"
            
            if upload_status in ["uploaded", "processing", "in_progress"]:
                logger.info(f"Video {video_id} is processing on YouTube (status: {upload_status})")
                return "PENDING"

            if upload_status not in ["processed", "succeeded"]:
                logger.warning(f"Video {video_id} is not fully processed (status: {upload_status})")
                return "FAILED"

            # Check thumbnail
            snippet = video.get("snippet", {})
            thumbnails = snippet.get("thumbnails", {})
            # Must have keys beyond 'default'
            if len(thumbnails.keys()) <= 1 and "default" in thumbnails:
                logger.warning(f"Video {video_id} has no custom thumbnail.")
                return "FAILED"

            # Check captions
            captions_response = youtube.captions().list(
                part="snippet",
                videoId=video_id
            ).execute()

            if not captions_response.get("items") or len(captions_response["items"]) == 0:
                logger.warning(f"Video {video_id} has no captions.")
                return "FAILED"

            # If all checks pass, update Firestore
            doc_ref = self.db.collection("content_items").document(doc_id)
            doc_ref.update({
                "youtube_verified": True,
                "verified_at": datetime.datetime.utcnow().isoformat()
            })
            logger.info(f"Verified video {video_id} for doc {doc_id}")
            return "VERIFIED"

        except Exception as e:
            logger.error(f"Error verifying video {video_id}: {e}")
            return "FAILED"

    def verify(self, doc_id: str, video_id: str, brand_id: str = "bd_threatpulse") -> bool:
        """
        Verify that a YouTube video is public, processed, has captions and a thumbnail.
        """
        return self.verify_status(doc_id, video_id, brand_id) == "VERIFIED"

