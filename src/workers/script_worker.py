"""
script_worker.py

Generates a structured video script using Gemini 2.5 Flash.
Input: brand profile + topic
Output dict: { hook, narration, visual_prompts: [{text, timestamp}] }
"""

import json
import os
from google.genai import types
from src.config.gemini_key_manager import GeminiKeyManager

MODEL_NAME = "gemini-1.5-flash-001"

SYSTEM_INSTRUCTIONS = """You are a short-form video scriptwriter. Given a brand's voice/style \
and a topic, produce a JSON object with exactly these keys:
- "hook": a 3-5 second attention-grabbing opening line
- "narration": the full narration text, written to be read aloud naturally
- "visual_prompts": an array of objects, each with "text" (a short scene description \
for image generation) and "timestamp" (approximate seconds into the narration this scene starts)

Return ONLY valid JSON, no markdown fences, no commentary.
"""


def generate_script(brand: dict, topic: str) -> dict:
    key_manager = GeminiKeyManager()

    content_angle = brand.get("content_angle", "")
    angle_prompt = f"Content angle & positioning: {content_angle}\n" if content_angle else ""

    prompt = (
        f"Brand: {brand['display_name']}\n"
        f"{angle_prompt}"
        f"Visual style guide: {brand['visual_style']}\n"
        f"Topic: {topic}\n\n"
        f"Write a 28-35 second short-form video script for this brand and topic. "
        f"Keep narration tight and punchy — this is for Reels/Shorts/TikTok feed "
        f"consumption where attention drops sharply after 30-40 seconds."
    )

    def op(client):
        return client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_INSTRUCTIONS,
                response_mime_type="application/json",
                temperature=0.7,
            ),
        )

    response = key_manager.execute(op)
    raw_text = response.text

    try:
        script = json.loads(raw_text)
    except json.JSONDecodeError as e:
        raise ValueError(f"Gemini returned non-JSON output: {raw_text[:300]}") from e

    # ... (rest of validation)
        if key not in script:
            raise ValueError(f"Script missing required key: {key}")

    return script
