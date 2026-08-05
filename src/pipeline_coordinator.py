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

        logger.info(f"[{content_id}] Synthesizing voice...")
        update_status(db, content_id, STATUS_GENERATING_AUDIO)
        audio_uri = synthesize_voice(
            script["narration"], brand_id, brand["voice_id"], content_id
        )
        update_status(db, content_id, STATUS_GENERATING_AUDIO, audio_uri=audio_uri)

        logger.info(f"[{content_id}] Generating images...")
        update_status(db, content_id, STATUS_GENERATING_IMAGES)
        image_uris = generate_images(script["visual_prompts"], brand, content_id)
        update_status(db, content_id, STATUS_GENERATING_IMAGES, image_uris=image_uris)

        logger.info(f"[{content_id}] Rendering final video...")
        update_status(db, content_id, STATUS_RENDERING)
        final_uri, srt_uri = render_video(script, audio_uri, image_uris, brand_id, content_id)

        logger.info(f"[{content_id}] Generating full publishing package...")
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
    brand_id = os.environ["BRAND_ID"]
    topic = os.environ["TOPIC"]
    content_id = os.environ["CONTENT_ID"]

    run_pipeline(brand_id, topic, content_id)
    # Process exits here — Cloud Run Job execution ends, no listener left running.
