"""
firestore_schema.py

Defines brand profiles and content_items status lifecycle for FRIDAY Media OS.
Collections:
  - brands: voice_id, visual_style, target platforms, hex colors per brand
  - content_items: pipeline execution status, script text, GCS asset URIs
"""

import os
from google.cloud import firestore

# --- Status lifecycle for content_items ---
STATUS_DRAFT = "draft"
STATUS_GENERATING_SCRIPT = "generating_script"
STATUS_GENERATING_AUDIO = "generating_audio"
STATUS_GENERATING_IMAGES = "generating_images"
STATUS_RENDERING = "rendering"
STATUS_PUBLISHED = "published"
STATUS_FAILED = "failed"

# --- Brand presets ---
BRAND_PROFILES = {
    "wealthwise": {
        "brand_id": "WealthWise Online Daily",
        "display_name": "WealthWise Online Daily",
        "voice_id": "en-US-Neural2-D",
        "visual_style": (
            "Wall Street aesthetic, dark navy stock market trading chart overlays, "
            "8k lighting, professional financial news style"
        ),
        "content_angle": "Actionable personal finance, wealth building, and index fund investing tips.",
        "hex_primary": "#0B0F19",
        "hex_accent": "#10B981",
        "target_platforms": ["youtube", "tiktok"],
        "target_duration_seconds": 30,
    },
    "kids_universe": {
        "brand_id": "Tiny Sparks",
        "display_name": "Tiny Sparks",
        "voice_id": "en-US-Journey-F",
        "visual_style": (
            "Vibrant 3D Pixar-style cartoon illustration, warm pastel colors, "
            "soft magical lighting, friendly rounded characters"
        ),
        "content_angle": "Fun, curious, educational science and nature facts for young children.",
        "hex_primary": "#FFF7ED",
        "hex_accent": "#F97316",
        "target_platforms": ["youtube"],
        "target_duration_seconds": 30,
    },
    "bd_threatpulse": {
        "brand_id": "bd_threatpulse",
        "display_name": "BD ThreatPulse",
        "voice_id": "en-US-Neural2-I",
        "visual_style": (
            "Executive boardroom aesthetic, dark navy background, subtle cybersecurity "
            "network node and data protection iconography, authoritative corporate briefing style"
        ),
        "content_angle": (
            "Educate C-suite executives on foundational technology and cybersecurity concepts "
            "in plain language — NOT generic AI hype content. Tone: authoritative, boardroom-briefing "
            "style, focused on business risk and decision-making relevance."
        ),
        "hex_primary": "#0B132B",
        "hex_accent": "#00B4D8",
        "target_platforms": ["youtube", "tiktok", "instagram"],
        "target_duration_seconds": 30,
    },
    "philosophy": {
        "brand_id": "The Thinking Room",
        "display_name": "The Thinking Room",
        "voice_id": "en-US-Neural2-I",
        "visual_style": (
            "Moody dark marble texture, dramatic chiaroscuro lighting, "
            "classical sculpture aesthetic"
        ),
        "content_angle": "Stoic wisdom, practical ancient philosophy, and self-mastery insights.",
        "hex_primary": "#131722",
        "hex_accent": "#C084FC",
        "target_platforms": ["youtube", "instagram"],
        "target_duration_seconds": 30,
    },
}


def get_db(project_id: str | None = None) -> firestore.Client:
    pid = project_id or os.environ.get("GCP_PROJECT_ID", "friday-media-prod")
    return firestore.Client(project=pid)


def seed_brands(db: firestore.Client) -> None:
    """Run once after Firestore creation to populate brand presets."""
    for brand_id, profile in BRAND_PROFILES.items():
        db.collection("brands").document(brand_id).set(profile, merge=True)


def get_brand(db: firestore.Client, brand_id: str) -> dict:
    doc = db.collection("brands").document(brand_id).get()
    if not doc.exists:
        raise ValueError(f"Unknown brand_id: {brand_id}")
    return doc.to_dict()


def create_content_item(db: firestore.Client, content_id: str, brand_id: str, topic: str) -> None:
    db.collection("content_items").document(content_id).set({
        "brand_id": brand_id,
        "topic": topic,
        "status": STATUS_DRAFT,
        "created_at": firestore.SERVER_TIMESTAMP,
        "updated_at": firestore.SERVER_TIMESTAMP,
    })
    # Also initialize content_queue doc
    db.collection("content_queue").document(content_id).set({
        "brand_id": brand_id,
        "topic": topic,
        "status": "QUEUED",
        "created_at": firestore.SERVER_TIMESTAMP,
        "updated_at": firestore.SERVER_TIMESTAMP,
    })


def update_status(db: firestore.Client, content_id: str, status: str, **extra_fields) -> None:
    # 1. Update content_items
    doc_ref = db.collection("content_items").document(content_id)
    payload = {"status": status, "updated_at": firestore.SERVER_TIMESTAMP, **extra_fields}
    doc_ref.set(payload, merge=True)

    # 2. Update content_queue status
    queue_ref = db.collection("content_queue").document(content_id)
    status_map = {
        STATUS_DRAFT: "QUEUED",
        STATUS_GENERATING_SCRIPT: "GENERATING",
        STATUS_GENERATING_AUDIO: "VOICE_READY",
        STATUS_GENERATING_IMAGES: "IMAGES_READY",
        STATUS_RENDERING: "RENDERING",
        STATUS_PUBLISHED: "READY",
        STATUS_FAILED: "FAILED"
    }
    queue_status = status_map.get(status, "QUEUED")
    
    queue_payload = {
        "status": queue_status,
        "updated_at": firestore.SERVER_TIMESTAMP
    }
    # Map intermediate states based on extra fields
    if "script" in extra_fields:
        queue_payload["status"] = "SCRIPT_READY"
    if "caption" in extra_fields or "hashtags" in extra_fields:
        queue_payload["status"] = "METADATA_READY"
        
    queue_ref.set(queue_payload, merge=True)


def update_brand_memory(db: firestore.Client, brand_id: str, content_id: str, topic: str, metadata: dict, video_uri: str) -> None:
    """Updates the persistent brand_memory collection upon successful pipeline completion."""
    mem_ref = db.collection("brand_memory").document(brand_id)
    mem_doc = mem_ref.get()
    
    memory = {
        "recent_topics": [],
        "recent_titles": [],
        "recent_keywords": [],
        "recent_categories": [],
        "last_200_videos": [],
        "performance_metrics": {},
        "best_performing_topics": [],
        "worst_performing_topics": [],
        "duplicate_similarity_cache": {},
        "last_publish_dates": {},
        "last_generated_metadata": {}
    }
    
    if mem_doc.exists:
        memory.update(mem_doc.to_dict())
        
    # Append new topic
    if topic not in memory["recent_topics"]:
        memory["recent_topics"].append(topic)
        memory["recent_topics"] = memory["recent_topics"][-50:]
        
    # Extract title
    title = metadata.get("title", "")
    if not title and "title_suggestions" in metadata:
        titles = metadata["title_suggestions"]
        title = titles[0] if titles else ""
    if title and title not in memory["recent_titles"]:
        memory["recent_titles"].append(title)
        memory["recent_titles"] = memory["recent_titles"][-50:]
        
    # Extract keywords/hashtags
    for kw in metadata.get("hashtags", []):
        clean_kw = kw.replace("#", "").strip()
        if clean_kw and clean_kw not in memory["recent_keywords"]:
            memory["recent_keywords"].append(clean_kw)
    memory["recent_keywords"] = memory["recent_keywords"][-100:]
    
    # Append to last 200 videos
    import datetime
    video_entry = {
        "content_id": content_id,
        "topic": topic,
        "title": title,
        "video_uri": video_uri,
        "timestamp": datetime.datetime.now(datetime.UTC)
    }
    memory["last_200_videos"].append(video_entry)
    memory["last_200_videos"] = memory["last_200_videos"][-200:]
    
    # Set dates & metadata
    memory["last_publish_dates"][content_id] = datetime.datetime.now(datetime.UTC)
    memory["last_generated_metadata"] = metadata
    
    mem_ref.set(memory)


def seed_automation(db: firestore.Client) -> None:
    """Populates brand_profiles, automation_settings, and default memory configurations."""
    brand_configs = {
        "bd_threatpulse": {
            "brand_id": "bd_threatpulse",
            "display_name": "BD ThreatPulse",
            "description": "Authoritative corporate cybersecurity briefing channel for C-level executives.",
            "audience": "C-suite executives, CISOs, technology directors, business leaders.",
            "tone": "Authoritative, sophisticated, boardroom-briefing style.",
            "voice": "en-US-Neural2-I",
            "language": "English",
            "primary_platforms": ["YouTube", "TikTok"],
            "publish_frequency_per_day": 4,
            "publish_windows": ["06:00-08:00", "10:00-12:00", "14:00-16:00", "18:00-21:00"],
            "preferred_video_duration": 30,
            "cta": "For strategic enterprise security briefings, subscribe to BD ThreatPulse.",
            "avoid_topics": ["fluffy AI hype", "generic tech predictions"],
            "categories": ["Technology", "Cybersecurity", "Risk Management"],
            "preferred_keywords": ["CISO", "cybersecurity", "enterprise risk", "data breach"],
            "image_style": "subtle cybersecurity network node and data protection iconography",
            "thumbnail_style": "minimalist business graphic with bold headline",
            "metadata_style": "boardroom briefing",
            "seo_style": "executive summary",
            "never_repeat_similarity": 0.8,
            "history_window": 30,
            "topic_strategy": "hybrid",
            "enable_cc": True,
            "enable_hashtags": True,
            "enable_thumbnail_generation": True,
            "enable_seo": True,
            "enable_ai_metadata": True
        },
        "wealthwise": {
            "brand_id": "wealthwise",
            "display_name": "WealthWise Daily",
            "description": "Practical personal finance, wealth building, and index fund investing tips channel.",
            "audience": "Individual investors, personal finance enthusiasts, retail traders.",
            "tone": "Clean, professional, and practical personal finance tone.",
            "voice": "en-US-Neural2-D",
            "language": "English",
            "primary_platforms": ["YouTube"],
            "publish_frequency_per_day": 4,
            "publish_windows": ["06:00-08:00", "10:00-12:00", "14:00-16:00", "18:00-21:00"],
            "preferred_video_duration": 30,
            "cta": "Start your wealth building journey today with WealthWise Daily.",
            "avoid_topics": ["get-rich-quick schemes", "crypto pump and dumps"],
            "categories": ["Finance", "Investing", "Wealth Building"],
            "preferred_keywords": ["index funds", "investing tips", "personal finance", "savings"],
            "image_style": "Wall Street aesthetic, dark navy stock market trading chart overlays",
            "thumbnail_style": "high CTR bold financial text overlay",
            "metadata_style": "practical news",
            "seo_style": "high traffic keywords",
            "never_repeat_similarity": 0.8,
            "history_window": 30,
            "topic_strategy": "ai",
            "enable_cc": True,
            "enable_hashtags": True,
            "enable_thumbnail_generation": True,
            "enable_seo": True,
            "enable_ai_metadata": True
        },
        "kids_universe": {
            "brand_id": "kids_universe",
            "display_name": "Tiny Sparks",
            "description": "Fun, curious, educational science and nature facts for young children.",
            "audience": "Curious children, parents, and educators.",
            "tone": "Creative, fun, engaging, safe, and highly visual.",
            "voice": "en-US-Journey-F",
            "language": "English",
            "primary_platforms": ["YouTube"],
            "publish_frequency_per_day": 4,
            "publish_windows": ["06:00-08:00", "10:00-12:00", "14:00-16:00", "18:00-21:00"],
            "preferred_video_duration": 30,
            "cta": "Subscribe to Tiny Sparks for more fun learning adventures!",
            "avoid_topics": ["unsafe content", "complex academic theories"],
            "categories": ["Education", "Science", "Nature"],
            "preferred_keywords": ["science for kids", "nature facts", "fun learning"],
            "image_style": "Vibrant 3D Pixar-style cartoon illustration, warm pastel colors",
            "thumbnail_style": "bright friendly title overlay with cute character",
            "metadata_style": "educational and playful",
            "seo_style": "family friendly keywords",
            "never_repeat_similarity": 0.8,
            "history_window": 30,
            "topic_strategy": "ai",
            "enable_cc": True,
            "enable_hashtags": True,
            "enable_thumbnail_generation": True,
            "enable_seo": True,
            "enable_ai_metadata": True
        },
        "philosophy": {
            "brand_id": "philosophy",
            "display_name": "The Thinking Room",
            "description": "Timeless Stoic wisdom, practical ancient philosophy, and self-mastery insights.",
            "audience": "Thinkers, professionals, self-improvement seekers.",
            "tone": "Reflective, calm, classical, wise.",
            "voice": "en-US-Neural2-I",
            "language": "English",
            "primary_platforms": ["YouTube", "Instagram"],
            "publish_frequency_per_day": 4,
            "publish_windows": ["06:00-08:00", "10:00-12:00", "14:00-16:00", "18:00-21:00"],
            "preferred_video_duration": 30,
            "cta": "Subscribe to The Thinking Room for daily philosophical reflections.",
            "avoid_topics": ["partisan politics", "unverified modern self-help jargon"],
            "categories": ["Philosophy", "Stoicism", "Self-Mastery"],
            "preferred_keywords": ["stoic quotes", "marcus aurelius", "seneca", "self-mastery"],
            "image_style": "Moody dark marble texture, dramatic chiaroscuro lighting",
            "thumbnail_style": "moody typography with classical statue motif",
            "metadata_style": "philosophical essay",
            "seo_style": "timeless search terms",
            "never_repeat_similarity": 0.8,
            "history_window": 30,
            "topic_strategy": "ai",
            "enable_cc": True,
            "enable_hashtags": True,
            "enable_thumbnail_generation": True,
            "enable_seo": True,
            "enable_ai_metadata": True
        }
    }
    
    for b_id, profile in brand_configs.items():
        db.collection("brand_profiles").document(b_id).set(profile)
        # Keep brands synced
        db.collection("brands").document(b_id).set(profile, merge=True)
        
    db.collection("automation_settings").document("global").set({
        "enabled": True,
        "daily_min": 1,
        "daily_max": 5,
        "timezone": "UTC",
        "publish_windows": ["09:00-11:00", "13:00-15:00", "18:00-21:00"],
        "randomize_publish_time": True,
        "fallback_mode": "hybrid",
        "retry_policy": {"max_retries": 3, "backoff_seconds": 300},
        "failure_notifications": {"email": "alert@fridaymedia.os"}
    })

