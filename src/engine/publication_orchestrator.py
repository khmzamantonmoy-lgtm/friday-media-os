import logging
from google.cloud import firestore
from src.workers.youtube_worker import upload_video as upload_youtube_video
from src.workers.facebook_worker import upload_facebook_reel
from src.auth.facebook_auth import MetaTokenInvalidError

logger = logging.getLogger(__name__)

class PublicationError(Exception):
    """General error for publishing failures on one or more platforms."""
    pass

class PublicationOrchestrator:
    def __init__(self, db: firestore.Client = None):
        self.db = db or firestore.Client()

    def publish_content_item(self, content_id: str, brand_cfg: dict, doc_data: dict, dry_run: bool = False) -> dict:
        """
        Orchestrates publishing to all enabled platforms sequentially.
        Adheres to idempotency and isolates platform-specific failures.
        """
        brand_id = brand_cfg.get("brand_id") or brand_cfg.get("id")
        platforms = brand_cfg.get("publishing_platforms", ["YouTube"])
        
        # Normalize platforms list to lowercase for robust checks
        normalized_platforms = [p.lower() for p in platforms]
        
        logger.info(f"[{content_id}] Starting orchestrator publishing for brand '{brand_id}' to platforms: {platforms}")
        
        results = {}
        errors = {}
        
        # Get Firestore document reference
        doc_ref = self.db.collection("content_items").document(content_id)
        
        # 1. YouTube Ingestion
        if "youtube" in normalized_platforms:
            youtube_video_id = doc_data.get("youtube_video_id")
            if youtube_video_id:
                logger.info(f"[{content_id}] YouTube upload already completed (youtube_video_id={youtube_video_id}). Bypassing.")
                results["youtube_video_id"] = youtube_video_id
                results["youtube_url"] = doc_data.get("youtube_url")
            else:
                try:
                    video_gs_uri = doc_data.get("final_video_uri")
                    srt_gs_uri = doc_data.get("srt_uri")
                    publishing_package = doc_data.get("publishing_package", {})
                    title = publishing_package.get("title") or doc_data.get("topic")
                    description = publishing_package.get("description") or "Automated upload."
                    tags = publishing_package.get("tags") or []
                    
                    if not video_gs_uri:
                        raise ValueError("Missing final_video_uri in content document")
                        
                    if dry_run:
                        logger.info(f"[{content_id}] [DRY_RUN] Simulating YouTube upload...")
                        yt_video_id = f"mock_yt_vid_{content_id}"
                        yt_url = f"https://www.youtube.com/watch?v={yt_video_id}"
                    else:
                        yt_url = upload_youtube_video(
                            channel=brand_id,
                            content_id=content_id,
                            video_gs_uri=video_gs_uri,
                            title=title,
                            description=description,
                            hashtags=tags,
                            srt_gs_uri=srt_gs_uri
                        )
                        yt_video_id = yt_url.split("watch?v=")[1].split("&")[0] if "watch?v=" in yt_url else yt_url
                    
                    # Persist YouTube publication immediately for state-machine idempotency
                    logger.info(f"[{content_id}] YouTube upload successful. Persisting to Firestore.")
                    doc_ref.update({
                        "youtube_video_id": yt_video_id,
                        "youtube_url": yt_url,
                        "youtube_published_at": firestore.SERVER_TIMESTAMP
                    })
                    results["youtube_video_id"] = yt_video_id
                    results["youtube_url"] = yt_url
                except Exception as e:
                    logger.exception(f"[{content_id}] YouTube upload failed: {e}")
                    errors["youtube"] = str(e)

        # 2. Facebook Ingestion
        if "facebook" in normalized_platforms:
            facebook_reel_id = doc_data.get("facebook_reel_id")
            if facebook_reel_id:
                logger.info(f"[{content_id}] Facebook upload already completed (facebook_reel_id={facebook_reel_id}). Bypassing.")
                results["facebook_reel_id"] = facebook_reel_id
                results["facebook_url"] = doc_data.get("facebook_url") or doc_data.get("facebook_reel_url")
            else:
                try:
                    page_id = brand_cfg.get("facebook_page_id")
                    if not page_id:
                        raise ValueError(f"Missing facebook_page_id in brand registry for brand '{brand_id}'")
                        
                    video_gs_uri = doc_data.get("final_video_uri")
                    publishing_package = doc_data.get("publishing_package", {})
                    title = publishing_package.get("title") or doc_data.get("topic")
                    description = publishing_package.get("description") or "Automated upload."
                    tags = publishing_package.get("tags") or []
                    
                    if not video_gs_uri:
                        raise ValueError("Missing final_video_uri in content document")

                    if dry_run:
                        logger.info(f"[{content_id}] [DRY_RUN] Simulating Facebook Reel upload...")
                        fb_reel_id = f"mock_fb_reel_{content_id}"
                    else:
                        fb_reel_id = upload_facebook_reel(
                            brand_id=brand_id,
                            page_id=page_id,
                            content_id=content_id,
                            video_gs_uri=video_gs_uri,
                            title=title,
                            description=description,
                            hashtags=tags,
                            video_state="PUBLISHED",
                            dry_run=False
                        )
                    
                    fb_url = f"https://www.facebook.com/reel/{fb_reel_id}"
                    
                    # Persist Facebook publication immediately for state-machine idempotency
                    logger.info(f"[{content_id}] Facebook upload successful. Persisting to Firestore.")
                    doc_ref.update({
                        "facebook_reel_id": fb_reel_id,
                        "facebook_reel_url": fb_url,
                        "facebook_published_at": firestore.SERVER_TIMESTAMP
                    })
                    results["facebook_reel_id"] = fb_reel_id
                    results["facebook_url"] = fb_url
                except MetaTokenInvalidError as token_err:
                    # Propagate OAuth 190 errors separately from general transient failures
                    logger.error(f"[{content_id}] Critical Meta Token Invalidation detected during Facebook publishing.")
                    raise token_err
                except Exception as e:
                    logger.exception(f"[{content_id}] Facebook upload failed: {e}")
                    errors["facebook"] = str(e)

        # 3. Handle Consolidated Failures
        if errors:
            err_msg = "; ".join([f"{platform}: {msg}" for platform, msg in errors.items()])
            raise PublicationError(f"Publishing failed for some platforms: {err_msg}")
            
        return results
