"""
learning_engine.py

Learning Engine for ATLAS.
Derives underlying mechanisms behind performance (Topic vs Execution vs Packaging vs Audience Failure).
"""

from typing import Dict, Any, List, Optional
import uuid
import json
import logging
from src.atlas.models import FailureType, EvidenceLevel, LearningInsight
from src.config.ai_request_manager import AIRequestManager
from src.atlas.config import MODEL_ROUTING

logger = logging.getLogger("learning_engine")


class LearningEngine:
    """
    ATLAS Learning Engine.
    Analyzes historical performance to extract underlying mechanics (topic, hook, narrative, visual framing).
    Distinguishes failure categories: TOPIC_FAILURE, EXECUTION_FAILURE, PACKAGING_FAILURE, AUDIENCE_FAILURE, INSUFFICIENT_DATA.
    """

    def __init__(self):
        self.ai_manager = AIRequestManager()

    def analyze_item_performance(
        self,
        brand_id: str,
        content_item: dict,
        performance: dict,
        baseline: dict
    ) -> LearningInsight:
        views = performance.get("views", 0)
        baseline_views = baseline.get("avg_views", 100)
        retention = performance.get("retention_rate", 0.0)
        
        # Categorize failure type if underperforming
        failure_type: Optional[FailureType] = None
        if views < baseline_views * 0.5:
            # Low views but high retention = Packaging or Topic failure
            if retention > 0.60:
                failure_type = FailureType.PACKAGING_FAILURE
            # Low views and low retention = Execution or Topic failure
            elif retention < 0.30:
                failure_type = FailureType.EXECUTION_FAILURE
            else:
                failure_type = FailureType.TOPIC_FAILURE
        elif views == 0:
            failure_type = FailureType.INSUFFICIENT_DATA

        prompt = f"""
You are the ATLAS Strategic Learning Engine for channel '{brand_id}'.

CONTENT ITEM DETAILS:
Topic: {content_item.get('topic')}
Caption: {content_item.get('caption')}

PERFORMANCE DATA:
Views: {views} (Baseline Average: {baseline_views})
Retention: {retention}
Failure Category Identified: {failure_type.value if failure_type else 'SUCCESS / WINNER'}

Determine the UNDERLYING MECHANISM behind this result:
- What specific topic, hook, narrative, or pacing mechanism caused this outcome?
- Do NOT simply state 'make more videos like this'.
- State the root cause mechanism and derive ONE concrete controlled follow-up action.

Return JSON matching:
{{
    "underlying_mechanism": "Explanation of mechanism",
    "derived_action": "Concrete next test or strategic adjustment",
    "evidence_level": "OBSERVED" | "INFERRED" | "HYPOTHESIS"
}}
"""

        def _op(client):
            return client.models.generate_content(
                model=MODEL_ROUTING["HIGH_REASONING"],
                contents=prompt,
                config={"response_mime_type": "application/json"}
            )

        try:
            res = self.ai_manager.execute(_op)
            data = json.loads(res.text)
            
            ev_str = data.get("evidence_level", "INFERRED").upper()
            ev_enum = EvidenceLevel.INFERRED
            if ev_str == "OBSERVED":
                ev_enum = EvidenceLevel.OBSERVED
            elif ev_str == "HYPOTHESIS":
                ev_enum = EvidenceLevel.HYPOTHESIS

            return LearningInsight(
                insight_id=f"insight_{uuid.uuid4().hex[:6]}",
                brand_id=brand_id,
                evidence_level=ev_enum,
                underlying_mechanism=data.get("underlying_mechanism", "Standard performance trajectory."),
                failure_type=failure_type,
                derived_action=data.get("derived_action", "Continue monitoring metrics.")
            )

        except Exception as e:
            logger.warning(f"Learning Engine analysis failed: {e}. Returning fallback insight.")
            return LearningInsight(
                insight_id=f"insight_{uuid.uuid4().hex[:6]}",
                brand_id=brand_id,
                evidence_level=EvidenceLevel.HYPOTHESIS,
                underlying_mechanism=f"Fallback insight due to analysis error: {e}",
                failure_type=failure_type,
                derived_action="Maintain baseline strategy."
            )
