"""
google_agent_client.py

Google Agent Platform integration for FRIDAY Media OS.
Maps each brand to its corresponding permanent Google Editorial Agent
and requests structured editorial decisions based on brand profile, memory,
and real-time context.
"""

import os
import json
import logging
from google import genai
from google.genai import types

logger = logging.getLogger("google_agent_client")

AGENT_MAPPING = {
    "bd_threatpulse": {
        "agent_name": "BD ThreatPulse Editorial AI",
        "role": "Chief Cybersecurity & Enterprise Tech Editor",
        "system_instruction": (
            "You are BD ThreatPulse Editorial AI, an authoritative corporate technology and cybersecurity editor. "
            "Your audience consists of CISOs, CIOs, and executive leadership. "
            "You evaluate enterprise risk, zero-day vulnerabilities, strategic compliance, and emerging tech threats. "
            "Determine whether breaking security news requires an emergency alert briefing, or produce an evergreen "
            "executive technology breakdown. Never produce fluff or generic hype."
        ),
    },
    "wealthwise": {
        "agent_name": "WealthWise Financial Intelligence AI",
        "role": "Chief Financial Analyst & Wealth Strategist",
        "system_instruction": (
            "You are WealthWise Financial Intelligence AI, a Wall Street wealth building strategist. "
            "Your audience consists of retail investors, professionals, and wealth builders. "
            "You evaluate market movements, portfolio strategy, index fund investing, macroeconomic trends, and inflation hedging. "
            "Determine whether market volatility warrants a breaking briefing or produce an evergreen personal finance guide."
        ),
    },
    "kids_universe": {
        "agent_name": "Kids Universe Learning AI",
        "role": "Lead Educational Science & Nature Director",
        "system_instruction": (
            "You are Kids Universe Learning AI, a creative educational director for young children. "
            "Your audience consists of curious kids, parents, and educators. "
            "You explain fascinating science facts, nature phenomena, space exploration, and animal wonders. "
            "Keep content fun, engaging, safe, and highly visual."
        ),
    },
    "philosophy": {
        "agent_name": "Philosophy Reflection AI",
        "role": "Senior Classical Philosophy Scholar",
        "system_instruction": (
            "You are Philosophy Reflection AI, a classical Stoic and philosophical scholar. "
            "Your audience consists of thinkers, professionals, and seekers of self-mastery. "
            "You unpack timeless philosophical quotes, ancient wisdom (Marcus Aurelius, Seneca, Epictetus), and modern application."
        ),
    },
}


class GoogleAgentClient:
    def __init__(self, project_id: str | None = None, location: str = "us-central1"):
        self.project_id = project_id or os.environ.get("GCP_PROJECT_ID", "friday-media-prod")
        self.location = location
        self.client = genai.Client(
            vertexai=True,
            project=self.project_id,
            location=self.location,
        )

    def invoke_agent(
        self,
        brand_id: str,
        brand_profile: dict,
        brand_memory: dict,
        calendar_topic: str | None = None,
    ) -> dict:
        """
        Invokes the dedicated Google Agent for the brand to receive a structured
        editorial decision package (Topic, Verification, Reasoning, SEO, Scene Plan).
        """
        agent_info = AGENT_MAPPING.get(
            brand_id,
            {
                "agent_name": f"{brand_id.title()} Editorial AI",
                "role": "Content Strategist",
                "system_instruction": f"You are the autonomous content agent for {brand_profile.get('display_name', brand_id)}.",
            },
        )

        recent_topics = brand_memory.get("recent_topics", [])
        recent_titles = brand_memory.get("recent_titles", [])
        recent_keywords = brand_memory.get("recent_keywords", [])
        last_200 = brand_memory.get("last_200_videos", [])

        calendar_context = ""
        if calendar_topic:
            calendar_context = (
                f"EDITORIAL CALENDAR ASSIGNMENT:\n"
                f"The human editor has requested this specific topic: '{calendar_topic}'.\n"
                f"Analyze and refine this topic for maximum performance."
            )
        else:
            calendar_context = (
                "EDITORIAL CALENDAR STATUS: Empty.\n"
                "You must autonomously decide whether breaking news or an evergreen strategic topic "
                "is most appropriate right now."
            )

        prompt = f"""
Agent: {agent_info['agent_name']} ({agent_info['role']})

BRAND IDENTITY:
- Display Name: {brand_profile.get('display_name', brand_id)}
- Target Audience: {brand_profile.get('audience', '')}
- Tone: {brand_profile.get('tone', '')}
- Angle: {brand_profile.get('content_angle', '')}
- Categories: {brand_profile.get('categories', [])}
- Avoid Topics: {brand_profile.get('avoid_topics', [])}
- Preferred Duration: {brand_profile.get('preferred_video_duration', 30)} seconds

EDITORIAL MEMORY & HISTORY:
- Recent Topics (Do NOT repeat): {json.dumps(recent_topics[-30:])}
- Recent Titles: {json.dumps(recent_titles[-30:])}
- Recent Keywords: {json.dumps(recent_keywords[-50:])}
- Total Published History Count: {len(last_200)}

{calendar_context}

REQUIREMENTS:
Generate a complete, verified editorial decision package. Return JSON matching this exact structure:
{{
    "agent_name": "{agent_info['agent_name']}",
    "topic": "Concise topic title (max 80 chars)",
    "category": "Primary category",
    "editorial_reasoning": "Detailed breakdown of why this topic was chosen and why it will perform well",
    "is_breaking_news": false,
    "confidence": 0.95,
    "quality_score": 0.92,
    "verification_status": "verified",
    "verification_sources": ["Official Documentation", "GCP Advisory / Industry Standard"],
    "similarity_score": 0.05,
    "seo_title": "Engaging Click-Worthy Title",
    "description": "Full YouTube video description with CTA and outline",
    "hashtags": ["#tag1", "#tag2", "#tag3"],
    "cta": "Subscribe for more insights",
    "script_narration": "Full narration script for TTS text-to-speech audio",
    "scene_plan": [
        {{"scene_id": 1, "duration": 5, "visual_prompt": "detailed image prompt", "text_overlay": "scene title"}},
        {{"scene_id": 2, "duration": 10, "visual_prompt": "detailed image prompt", "text_overlay": "key takeaway"}},
        {{"scene_id": 3, "duration": 10, "visual_prompt": "detailed image prompt", "text_overlay": "summary"}},
        {{"scene_id": 4, "duration": 5, "visual_prompt": "detailed image prompt", "text_overlay": "call to action"}}
    ]
}}
"""

        try:
            response = self.client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=agent_info["system_instruction"],
                    response_mime_type="application/json",
                    temperature=0.7,
                ),
            )
            data = json.loads(response.text)
            data["agent_name"] = agent_info["agent_name"]
            return data
        except Exception as e:
            logger.exception(f"Failed to invoke agent for brand {brand_id}")
            # Fallback output structure if API call fails
            return {
                "agent_name": agent_info["agent_name"],
                "topic": calendar_topic or f"Strategic Briefing: {brand_id}",
                "category": "General",
                "editorial_reasoning": f"Fallback execution due to error: {e}",
                "is_breaking_news": False,
                "confidence": 0.8,
                "quality_score": 0.85,
                "verification_status": "unverified",
                "verification_sources": ["System Default"],
                "similarity_score": 0.1,
                "seo_title": calendar_topic or f"Briefing for {brand_id}",
                "description": "Automated briefing.",
                "hashtags": [f"#{brand_id}"],
                "cta": "Subscribe for updates",
                "script_narration": f"Welcome to {brand_profile.get('display_name', brand_id)}. Today we discuss {calendar_topic or brand_id}.",
                "scene_plan": [],
            }
