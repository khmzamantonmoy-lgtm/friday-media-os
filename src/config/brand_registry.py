"""
brand_registry.py

Centralized Dynamic Brand & YouTube Channel Registry for FRIDAY Media OS.
Configures all operational parameters, Google Agent identities, secret references,
publishing targets, and threshold limits. Adding a new brand requires configuration only.
"""

BRAND_REGISTRY = {
    "bd_threatpulse": {
        "brand_id": "bd_threatpulse",
        "brand_name": "BD ThreatPulse",
        "google_agent_name": "BD ThreatPulse Editorial AI",
        "youtube_channel_name": "BD ThreatPulse Official",
        "client_secret_id": "bd-threatpulse-client-secret",
        "token_secret_id": "bd-threatpulse-token",
        "publishing_platforms": ["YouTube", "TikTok", "Instagram"],
        "auto_publish": True,
        "daily_target": 2,
        "priority": "high",
        "similarity_threshold": 0.80,
        "confidence_threshold": 0.70,
        "voice_id": "en-US-Neural2-I",
        "categories": ["Technology", "Cybersecurity", "Risk Management"],
        "topic_strategy": "hybrid",
    },
    "wealthwise": {
        "brand_id": "wealthwise",
        "brand_name": "WealthWise Daily",
        "google_agent_name": "WealthWise Financial Intelligence AI",
        "youtube_channel_name": "WealthWise Daily Official",
        "client_secret_id": "wealthwise-client-secret",
        "token_secret_id": "wealthwise-token",
        "publishing_platforms": ["YouTube", "TikTok"],
        "auto_publish": True,
        "daily_target": 1,
        "priority": "high",
        "similarity_threshold": 0.80,
        "confidence_threshold": 0.70,
        "voice_id": "en-US-Neural2-D",
        "categories": ["Finance", "Investing", "Wealth Building"],
        "topic_strategy": "ai",
    },
    "kids_universe": {
        "brand_name": "Tiny Sparks",
        "google_agent_name": "Tiny Sparks Learning AI",
        "youtube_channel_name": "Tiny Sparks",
        "client_secret_id": "tinysparks-client-secret",
        "token_secret_id": "tinysparks-token",
        "daily_target": 1,
        "priority": "medium",
        "similarity_threshold": 0.85,
        "confidence_threshold": 0.75,
        "voice_id": "en-US-Journey-F",
        "categories": ["Education", "Science", "Nature"],
        "topic_strategy": "ai",
    },
    "philosophy": {
        "brand_name": "The Thinking Room",
        "google_agent_name": "The Thinking Room Reflection AI",
        "youtube_channel_name": "The Thinking Room",
        "client_secret_id": "thinkingroom-client-secret",
        "token_secret_id": "thinkingroom-token",
        "publishing_platforms": ["YouTube", "Instagram"],
        "auto_publish": True,
        "daily_target": 1,
        "priority": "medium",
        "similarity_threshold": 0.80,
        "confidence_threshold": 0.70,
        "voice_id": "en-US-Neural2-I",
        "categories": ["Philosophy", "Stoicism", "Self-Mastery"],
        "topic_strategy": "ai",
    },
}


def get_brand_config(brand_id: str) -> dict:
    """Retrieves brand configuration from the centralized registry."""
    if brand_id not in BRAND_REGISTRY:
        raise ValueError(f"Unknown brand_id '{brand_id}'. Registered brands: {list(BRAND_REGISTRY.keys())}")
    return BRAND_REGISTRY[brand_id]
