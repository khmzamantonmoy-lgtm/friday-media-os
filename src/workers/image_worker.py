"""
image_worker.py

Generates vertical (9:16) background frames using Gemini 2.5 Flash Image.
Runs image generation in parallel threads to optimize pipeline latency.
"""

import os
import logging
from concurrent.futures import ThreadPoolExecutor
from google.genai import types
from google.cloud import storage
from google.auth import default
from src.config.ai_request_manager import AIRequestManager

logger = logging.getLogger("image_worker")

try:
    _, PROJECT_ID = default()
except Exception:
    PROJECT_ID = os.environ.get("GCP_PROJECT_ID", "friday-media-os")

BUCKET_NAME = os.environ.get("GCS_BUCKET_NAME", f"friday-media-assets-{PROJECT_ID}")
IMAGE_MODEL = "gemini-2.5-flash-image"


def generate_single_image(args) -> str:
    """Generates a single image frame and uploads it to GCS."""
    import time
    i, scene, brand, content_id = args
    key_manager = AIRequestManager()
    storage_client = storage.Client()
    bucket = storage_client.bucket(BUCKET_NAME)

    visual_style = brand.get("visual_style", "Modern, high quality, engaging short-form visuals")
    brand_id = brand.get("brand_id") or brand.get("id", "brand")

    full_prompt = (
        f"{visual_style}. Scene: {scene['text']}. "
        f"Vertical 9:16 aspect ratio, no text overlays."
    )

    def op(client):
        return client.models.generate_content(
            model=IMAGE_MODEL,
            contents=full_prompt,
            config=types.GenerateContentConfig(
                response_modalities=["IMAGE"],
            ),
        )

    logger.info(f"VERTEX_IMAGE_ADMITTED: content_id={content_id}, scene_index={i}")
    start_time = time.time()
    response = key_manager.execute(op)
    duration = time.time() - start_time
    logger.info(f"VERTEX_IMAGE_COMPLETED: content_id={content_id}, scene_index={i}, duration={duration:.2f}s")

    image_bytes = None
    for part in response.candidates[0].content.parts:
        if part.inline_data is not None:
            image_bytes = part.inline_data.data
            break

    if image_bytes is None:
        raise ValueError(f"No image returned for scene {i}: {scene['text'][:80]}")

    blob_path = f"{brand_id}/images/{content_id}_frame_{i}.png"
    blob = bucket.blob(blob_path)
    blob.upload_from_string(image_bytes, content_type="image/png")

    return f"gs://{BUCKET_NAME}/{blob_path}"


def generate_images(visual_prompts: list[dict], brand: dict, content_id: str) -> list[str]:
    """
    visual_prompts: list of {"text": ..., "timestamp": ...}
    Returns list of gs:// URIs, executing requests sequentially.
    """
    tasks = [(i, scene, brand, content_id) for i, scene in enumerate(visual_prompts)]
    
    # Enforce serialized concurrency of exactly 1 to avoid Vertex AI 429 rate limits
    max_workers = 1
    logger.info(f"Generating {len(tasks)} images sequentially (concurrency=1) for {content_id}...")

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # map preserves the original order of the tasks list
        results = list(executor.map(generate_single_image, tasks))

    return results
