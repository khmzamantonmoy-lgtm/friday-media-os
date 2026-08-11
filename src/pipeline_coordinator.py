"""
pipeline_coordinator.py

Orchestrates: script -> voice -> images -> render, writing progress to
Firestore at each stage. Runs as a Cloud Run Job — executes once per
invocation and exits. No web server, no persistent process.
"""

import os
import sys
import logging

from src.config.firestore_schema import (
    get_db,
    get_brand,
    create_content_item,
    update_status,
    STATUS_GENERATING_SCRIPT,
    STATUS_GENERATING_AUDIO,
    STATUS_GENERATING_IMAGES,
    STATUS_RENDERING,
    STATUS_PUBLISHED,
    STATUS_FAILED,
)
from src.workers.script_worker import generate_script
from src.workers.voice_worker import synthesize_voice
from src.workers.image_worker import generate_images
from src.workers.render_worker import render_video

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("pipeline_coordinator")


def run_pipeline(brand_id: str, topic: str, content_id: str) -> None:
    db = get_db()
    brand = get_brand(db, brand_id)
    create_content_item(db, content_id, brand_id, topic)

    try:
        # Check if pre-generated content exists from Google Agents
        content_ref = db.collection("content_items").document(content_id)
        content_doc = content_ref.get()
        c_data = content_doc.to_dict() if content_doc.exists else {}

        if c_data.get("script") and c_data.get("scene_plan"):
            logger.info(f"[{content_id}] Reusing agent-generated script and scene plan.")
            visual_prompts = []
            cumulative_time = 0
            for scene in c_data.get("scene_plan", []):
                visual_prompts.append({
                    "text": scene.get("visual_prompt", ""),
                    "timestamp": cumulative_time
                })
                cumulative_time += scene.get("duration", 5)
            
            script = {
                "narration": c_data.get("script"),
                "visual_prompts": visual_prompts
            }
            
            metadata = {
                "caption": c_data.get("caption") or "",
                "hashtags": c_data.get("hashtags") or [],
                "title_suggestions": [c_data.get("seo_title")] if c_data.get("seo_title") else [topic]
            }
        else:
            logger.info(f"[{content_id}] Generating script...")
            update_status(db, content_id, STATUS_GENERATING_SCRIPT)
            script = generate_script(brand, topic)

            logger.info(f"[{content_id}] Generating publishing metadata...")
            from src.workers.metadata_worker import generate_metadata
            metadata = generate_metadata(script, brand)

        update_status(
            db,
            content_id,
            STATUS_GENERATING_SCRIPT,
            script=script,
            caption=metadata["caption"],
            hashtags=metadata["hashtags"],
            title_suggestions=metadata["title_suggestions"],
        )

        from concurrent.futures import ThreadPoolExecutor
        
        logger.info(f"[{content_id}] Initiating parallel audio synthesis and image generation...")
        update_status(db, content_id, STATUS_GENERATING_IMAGES)
        
        with ThreadPoolExecutor(max_workers=2) as executor:
            future_voice = executor.submit(
                synthesize_voice, script["narration"], brand_id, brand["voice_id"], content_id
            )
            future_images = executor.submit(
                generate_images, script["visual_prompts"], brand, content_id
            )
            
            audio_uri = future_voice.result()
            image_uris = future_images.result()

        update_status(
            db,
            content_id,
            STATUS_GENERATING_IMAGES,
            audio_uri=audio_uri,
            image_uris=image_uris,
        )

        logger.info(f"[{content_id}] Rendering final video...")
        update_status(db, content_id, STATUS_RENDERING)
        final_uri, srt_uri = render_video(script, audio_uri, image_uris, brand_id, content_id)

        logger.info(f"[{content_id}] Generating full publishing package...")
        if c_data.get("seo_title") or c_data.get("caption"):
            publishing_package = {
                "title": c_data.get("seo_title") or topic,
                "description": c_data.get("caption") or "",
                "tags": c_data.get("hashtags") or []
            }
        else:
            try:
                from src.workers.metadata_worker import generate_publishing_metadata
                publishing_package = generate_publishing_metadata(brand, topic, script)
            except Exception as pe:
                logger.warning(f"[{content_id}] Failed to generate publishing package: {pe}")
                publishing_package = {}

        update_status(
            db, 
            content_id, 
            STATUS_PUBLISHED, 
            final_video_uri=final_uri, 
            srt_uri=srt_uri, 
            publishing_package=publishing_package
        )
        logger.info(f"[{content_id}] Done: {final_uri} (SRT: {srt_uri})")

        # Update brand memory upon successful generation
        try:
            from src.config.firestore_schema import update_brand_memory
            update_brand_memory(db, brand_id, content_id, topic, metadata, final_uri)
            logger.info(f"[{content_id}] Brand memory updated successfully.")
        except Exception as bme:
            logger.warning(f"[{content_id}] Failed to update brand memory: {bme}")

    except Exception as e:
        logger.exception(f"[{content_id}] Pipeline failed")
        update_status(db, content_id, STATUS_FAILED, error=str(e))
        sys.exit(1)


if __name__ == "__main__":
    import sys
    from google.cloud import firestore
    
    brand_id = os.environ.get("BRAND_ID")
    topic = os.environ.get("TOPIC")
    content_id = os.environ.get("CONTENT_ID")
    
    if not content_id:
        print("Error: CONTENT_ID environment variable not set.")
        sys.exit(1)
        
    db = firestore.Client()
    doc_ref = db.collection("content_items").document(content_id)
    doc = doc_ref.get()
    
    if doc.exists:
        data = doc.to_dict()
        auth_brand_id = data.get("brand_id")
        auth_topic = data.get("topic")
        print(f"Loaded authoritative Firestore state for {content_id}: brand_id={auth_brand_id}, topic={auth_topic}")
        
        # Execute the new incremental state-machine worker path
        from src.engine.brand_worker import BrandWorker
        worker = BrandWorker()
        worker.run_cycle_for_item(content_id)
    else:
        # Fallback to legacy run_pipeline for backward compatibility if doc doesn't exist
        print(f"Warning: Document {content_id} not found in Firestore. Running legacy pipeline coordinator.")
        if not brand_id or not topic:
            print("Error: BRAND_ID and TOPIC environment variables are required for legacy fallback.")
            sys.exit(1)
        run_pipeline(brand_id, topic, content_id)
    # Process exits here — Cloud Run Job execution ends, no listener left running.

