"""
metadata_worker.py

Generates AI-driven social media publishing packages using Gemini 2.5 Flash.
Supports both the new comprehensive publishing package and the legacy script-phase metadata format.
"""

import json
import os
from google.genai import types
from src.config.ai_request_manager import AIRequestManager

MODEL_NAME = "gemini-2.5-flash"

SYSTEM_INSTRUCTIONS = """You are an elite social media copywriter and growth marketer. Given a brand profile, a video topic, and the narration script, generate a comprehensive publishing metadata package.

CRITICAL TONE & STYLE RULES:
- AVOID ALL GENERIC AI CLICHES. Never use words like: 'unlock', 'delve', 'revolutionize', 'demystify', 'furthermore', 'tapestry', 'testament', 'beacon', 'supercharge', 'elevate', 'essential guide'.
- OPTIMIZE FOR HIGH CTR: Write hooks and titles that spark curiosity, address pain points, or offer high value, but avoid cheesy clickbait.
- ALIGN WITH BRAND VOICE:
  * For BD ThreatPulse: Use an authoritative, direct, and sophisticated boardroom-briefing tone. Focus on risk management, strategic impacts, and enterprise security. Avoid fluffy intro phrases.
  * For WealthWise Daily: Use a clean, professional, and practical personal finance tone. Direct, clear, value-driven.
  * For Kids Universe: Use a friendly, curious, and engaging tone suitable for children and parents.
  * For Philosophy / Stoicism: Use a grounded, serious, reflective, and thought-provoking tone.

Return ONLY a valid JSON object (no markdown, no code blocks) containing exactly these keys:
- "title": A high-CTR viral title (max 60 chars).
- "seo_title": Search engine optimized title including main keywords.
- "short_description": A punchy, one-sentence summary.
- "long_description": A detailed three-sentence summary explaining the value.
- "platform_caption": General copy optimized for engagement.
- "viral_hook": The first line of the caption to hook the scroller.
- "hashtags": List of 5-8 relevant hashtags (strings, without the '#' symbol).
- "keywords": List of search keywords.
- "cta": Primary call to action (e.g., 'Share this with your CISO' or 'Get our fund guide').
- "thumbnail_text": Text to overlay on the thumbnail image (max 4-5 words, high impact).
- "thumbnail_prompt": Text prompt for generating a matching high-quality thumbnail image.
- "thumbnail_colors": String describing the suggested thumbnail color palette (matching the brand colors).
- "target_audience": Description of the target viewer persona.
- "content_category": E.g. Technology, Personal Finance, Education.
- "estimated_reading_time": Estimated time to read description (e.g. "30 seconds").
- "suggested_publish_time": Best time to schedule this post.
- "youtube_tags": List of tags for YouTube metadata.
- "tiktok_caption": A short, viral caption optimized for TikTok.
- "instagram_caption": A visual-centric caption optimized for Instagram.
- "linkedin_caption": A professional post for LinkedIn explaining the business context.
- "facebook_caption": An engaging, community-focused caption for Facebook.
- "x_caption": A short post for X/Twitter within 280 characters.
- "suggested_comment": Suggested first comment (to pin) to drive engagement.
"""

def generate_publishing_metadata(brand: dict, topic: str, script: dict) -> dict:
    """
    Invokes Gemini to construct a complete social publishing package for a content item.
    """
    key_manager = AIRequestManager()

    prompt = (
        f"Brand: {brand.get('display_name', '')}\n"
        f"Brand Voice/Angle: {brand.get('content_angle', '')}\n"
        f"Topic: {topic}\n"
        f"Script Hook: {script.get('hook', '')}\n"
        f"Script Narration: {script.get('narration', '')}\n\n"
        f"Please write the publishing package for this video."
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
    raw_text = response.text.strip()
    
    try:
        metadata = json.loads(raw_text)
    except json.JSONDecodeError as e:
        raise ValueError(f"Gemini returned non-JSON publishing package: {raw_text[:300]}") from e

    # Ensure all required keys exist to prevent downstream KeyErrors
    keys = [
        "title", "seo_title", "short_description", "long_description", "platform_caption",
        "viral_hook", "hashtags", "keywords", "cta", "thumbnail_text", "thumbnail_prompt",
        "thumbnail_colors", "target_audience", "content_category", "estimated_reading_time",
        "suggested_publish_time", "youtube_tags", "tiktok_caption", "instagram_caption",
        "linkedin_caption", "facebook_caption", "x_caption", "suggested_comment"
    ]
    for k in keys:
        if k not in metadata:
            metadata[k] = "" if "caption" in k or "description" in k or "title" in k or k in ("cta", "viral_hook", "thumbnail_text", "thumbnail_prompt", "thumbnail_colors", "target_audience", "content_category", "estimated_reading_time", "suggested_publish_time", "suggested_comment") else []

    return metadata


def generate_metadata(script: dict, brand: dict) -> dict:
    """
    Backward-compatible legacy function invoked during script generation phase.
    Maps generated publishing package output to legacy dictionary format.
    """
    try:
        package = generate_publishing_metadata(brand, "General video", script)
        # Reconstruct hashtags list with '#' symbols if expected by legacy code, or keep clean
        hashtags = [f"#{tag}" if not tag.startswith("#") else tag for tag in package.get("hashtags", [])]
        return {
            "caption": package.get("platform_caption", ""),
            "hashtags": hashtags,
            "title_suggestions": [package.get("title", ""), package.get("seo_title", "")]
        }
    except Exception:
        # Robust fallback
        return {
            "caption": "Check out our latest video!",
            "hashtags": [f"#{brand.get('display_name', 'media').replace(' ', '')}"],
            "title_suggestions": ["Amazing Video", "Must Watch"]
        }
