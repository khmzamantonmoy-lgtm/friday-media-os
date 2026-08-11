"""
trend_intel.py

Trend Intelligence & Topic Opportunity Engine for ATLAS.
"""

from typing import Dict, Any, List
import json
import logging
from src.config.ai_request_manager import AIRequestManager
from src.atlas.config import MODEL_ROUTING

logger = logging.getLogger("trend_intel")


class TrendIntelligence:
    """
    Analyzes brand context, audience demand, and market trends to discover
    high-opportunity topics and hook directions.
    """

    def __init__(self):
        self.ai_manager = AIRequestManager()

    def discover_opportunities(self, brand_id: str, brand_profile: dict, brand_memory: dict) -> List[Dict[str, Any]]:
        recent_topics = brand_memory.get("recent_topics", [])
        categories = brand_profile.get("categories", [])
        content_angle = brand_profile.get("content_angle", "")

        prompt = f"""
You are the ATLAS Trend Intelligence Engine for '{brand_profile.get('display_name', brand_id)}'.
Content Angle: {content_angle}
Categories: {categories}
Recent Topics: {json.dumps(recent_topics[-15:])}

Generate 3 high-impact, fresh topic opportunities that are trending and highly relevant for the US audience right now.
Return JSON array of objects with keys:
- topic: specific title
- hook_direction: immediate opening hook idea
- emotional_trigger: curiosity, urgency, empowerment, or reflection
- estimated_demand_score: number between 0.8 and 1.0
"""

        def _op(client):
            return client.models.generate_content(
                model=MODEL_ROUTING["FAST_LOW_COST"],
                contents=prompt,
                config={"response_mime_type": "application/json"}
            )

        try:
            res = self.ai_manager.execute(_op)
            return json.loads(res.text)
        except Exception as e:
            logger.warning(f"Trend intelligence generation failed: {e}. Returning fallback opportunity.")
            return [{
                "topic": f"Strategic Analysis for {brand_profile.get('display_name', brand_id)}",
                "hook_direction": "What most professionals miss about this key trend...",
                "emotional_trigger": "curiosity",
                "estimated_demand_score": 0.85
            }]
