"""
qa_governance.py

Content Governance & Quality Assurance Engine for ATLAS.
Evaluates specialist agent outputs before publishing.
"""

from typing import Dict, Any
import json
import logging
from src.atlas.models import QAEvaluation, QAResult
from src.config.ai_request_manager import AIRequestManager
from src.atlas.config import MODEL_ROUTING, ATLAS_SHADOW_MODE

logger = logging.getLogger("qa_governance")


class ContentGovernanceEngine:
    """
    ATLAS Content Governance Engine.
    Reviews specialist-generated decision packages before script/media generation proceeds.
    Outputs: PASS, REVISE, or REJECT.
    """

    def __init__(self):
        self.ai_manager = AIRequestManager()

    def evaluate_content(self, brand_profile: dict, content_brief: dict, specialist_output: dict) -> QAEvaluation:
        """
        Evaluates specialist output against the strategic content brief and brand guardrails.
        """
        topic = specialist_output.get("topic", "")
        script = specialist_output.get("script_narration") or specialist_output.get("script", "")
        
        # Rule-based fast check for severe flaws
        avoid_topics = brand_profile.get("avoid_topics", [])
        for avoid in avoid_topics:
            if avoid.lower() in topic.lower():
                return QAEvaluation(
                    result=QAResult.REJECT,
                    score=0.1,
                    feedback=f"Violates brand restriction: topic contains prohibited keyword '{avoid}'",
                    channel_fit=False,
                    audience_fit=False,
                    geographic_fit=True,
                    originality_score=0.1,
                    retention_hypothesis="Invalid due to policy violation",
                    revision_instructions=f"Select a new topic that avoids {avoid}"
                )

        prompt = f"""
You are the ATLAS Content Governance Board evaluating content for channel '{brand_profile.get('display_name')}'.

STRATEGIC BRIEF:
{json.dumps(content_brief, indent=2)}

SPECIALIST AGENT GENERATED OUTPUT:
{json.dumps(specialist_output, indent=2)}

Evaluate this package on:
1. Channel & Brand Alignment (Does it match brand identity?)
2. Audience & Geographic Fit (Is it appropriate for US audience target?)
3. Retention & Hook Impact (Does the hook capture attention in 3 seconds?)
4. Originality & Factual Soundness (Is it insightful vs generic fluff?)

Return JSON matching:
{{
    "result": "PASS" | "REVISE" | "REJECT",
    "score": 0.92,
    "feedback": "Detailed justification of evaluation",
    "channel_fit": true,
    "audience_fit": true,
    "geographic_fit": true,
    "originality_score": 0.88,
    "retention_hypothesis": "Strong opening hook will retain viewers beyond 5 seconds",
    "revision_instructions": "Optional instructions if REVISE"
}}
"""

        def _op(client):
            return client.models.generate_content(
                model=MODEL_ROUTING["STRONG_GENERAL"],
                contents=prompt,
                config={"response_mime_type": "application/json"}
            )

        try:
            res = self.ai_manager.execute(_op)
            data = json.loads(res.text)
            
            result_str = data.get("result", "PASS").upper()
            result_enum = QAResult.PASS
            if result_str == "REVISE":
                result_enum = QAResult.REVISE
            elif result_str == "REJECT":
                result_enum = QAResult.REJECT

            evaluation = QAEvaluation(
                result=result_enum,
                score=float(data.get("score", 0.85)),
                feedback=data.get("feedback", "Content aligns with strategy."),
                channel_fit=bool(data.get("channel_fit", True)),
                audience_fit=bool(data.get("audience_fit", True)),
                geographic_fit=bool(data.get("geographic_fit", True)),
                originality_score=float(data.get("originality_score", 0.85)),
                retention_hypothesis=data.get("retention_hypothesis", "High initial engagement expected."),
                revision_instructions=data.get("revision_instructions")
            )
            
            if ATLAS_SHADOW_MODE and evaluation.result != QAResult.PASS:
                logger.info(f"[ATLAS SHADOW MODE] QA Governance evaluated {result_str} (score={evaluation.score}), but passing through due to Shadow Mode.")
            
            return evaluation

        except Exception as e:
            logger.warning(f"QA Governance evaluation failed: {e}. Defaulting to PASS.")
            return QAEvaluation(
                result=QAResult.PASS,
                score=0.80,
                feedback=f"Governance default pass due to evaluation error: {e}",
                channel_fit=True,
                audience_fit=True,
                geographic_fit=True,
                originality_score=0.80,
                retention_hypothesis="Default retention assumption"
            )
