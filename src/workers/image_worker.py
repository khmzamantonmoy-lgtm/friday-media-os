"""
image_worker.py

Generates vertical (9:16) background frames using Gemini 2.5 Flash Image
(the current replacement for the retired Imagen 3 endpoint), prepending
the brand's visual_style to every prompt. Uploads each frame to GCS and
returns the list of gs:// URIs.
"""

import os
import time
import logging
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


def generate_images(visual_prompts: list[dict], brand: dict, content_id: str) -> list[str]:
    """
    visual_prompts: list of {"text": ..., "timestamp": ...} from script_worker output
    Returns list of gs:// URIs, one per scene, in the same order as visual_prompts.
    """
    key_manager = AIRequestManager()
    storage_client = storage.Client()
    bucket = storage_client.bucket(BUCKET_NAME)

    uris = []
    for i, scene in enumerate(visual_prompts):
        if i > 0:
            time.sleep(2.0)
        full_prompt = (
            f"{brand['visual_style']}. Scene: {scene['text']}. "
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

        response = key_manager.execute(op)

        image_bytes = None
        for part in response.candidates[0].content.parts:
            if part.inline_data is not None:
                image_bytes = part.inline_data.data
                break

        if image_bytes is None:
            raise ValueError(f"No image returned for scene {i}: {scene['text'][:80]}")

        blob_path = f"{brand['brand_id']}/images/{content_id}_frame_{i}.png"
        blob = bucket.blob(blob_path)
        blob.upload_from_string(image_bytes, content_type="image/png")

        uris.append(f"gs://{BUCKET_NAME}/{blob_path}")

    return uris
