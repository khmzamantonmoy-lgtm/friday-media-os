"""
orchestrator.py

ATLAS — Audience, Trend & Learning Adaptive Strategy Orchestrator.

Main entry point for the ATLAS strategic intelligence layer.
Sits ABOVE the four specialist agents and governs the full
content strategy → brief → specialist → QA → analytics → learning loop.

Shadow Mode: ATLAS observes, logs, and advises but does not block production.
Active Mode: ATLAS enforces strategic briefs and QA governance.
"""

from typing import Dict, Any, Optional
import uuid
import json
import datetime
import logging

from src.config.brand_registry import BRAND_REGISTRY, get_brand_config
from src.config.ai_request_manager import AIRequestManager
from src.atlas.config import MODEL_ROUTING, ATLAS_SHADOW_MODE, DEFAULT_TARGET_GEOGRAPHY
from src.atlas.models import ContentBrief, QAResult, PortfolioCategory

from src.atlas.intelligence.audience_intel import AudienceIntelligence
from src.atlas.intelligence.trend_intel import TrendIntelligence
from src.atlas.strategy.content_strategy import ContentStrategyEngine
from src.atlas.governance.qa_governance import ContentGovernanceEngine
from src.atlas.memory.strategic_memory import StrategicMemory
from src.atlas.learning.performance_intel import PerformanceIntelligence
from src.atlas.learning.learning_engine import LearningEngine

logger = logging.getLogger("atlas.orchestrator")


class ATLASOrchestrator:
    """
    ATLAS Strategic Intelligence Orchestrator.

    Decision hierarchy:
    1. Read strategic memory for the channel.
    2. Evaluate audience & geographic context.
    3. Discover trend opportunities.
    4. Select portfolio category.
    5. Construct structured ContentBrief.
    6. Route to correct specialist agent.
    7. Evaluate specialist output via QA Governance.
    8. Allow or block publishing (Shadow Mode = always allow with warning).
    9. After publishing: ingest performance data.
    10. Run learning engine to derive mechanisms.
    11. Update strategic memory.
    """

    def __init__(self):
        self.ai_manager = AIRequestManager()
        self.trend_intel = TrendIntelligence()
        self.strategy_engine = ContentStrategyEngine()
        self.qa_engine = ContentGovernanceEngine()
        self.strategic_memory = StrategicMemory()
        self.performance_intel = PerformanceIntelligence()
        self.learning_engine = LearningEngine()

    # ─────────────────────────────────────────────────────────────────────────
    # Phase 0: Discovery — confirm which brands/agents are configured
    # ─────────────────────────────────────────────────────────────────────────

    def discover_agents(self) -> Dict[str, Any]:
        """Returns the map of configured specialist agents and their identities."""
        from src.agents.google_agent_client import AGENT_MAPPING
        agents = {}
        for brand_id, agent_info in AGENT_MAPPING.items():
            brand_cfg = BRAND_REGISTRY.get(brand_id, {})
            agents[brand_id] = {
                "agent_name": agent_info["agent_name"],
                "role": agent_info["role"],
                "brand_name": brand_cfg.get("brand_name", brand_id),
                "categories": brand_cfg.get("categories", []),
                "platforms": brand_cfg.get("publishing_platforms", []),
            }
        logger.info(f"ATLAS discovered {len(agents)} specialist agents: {list(agents.keys())}")
        return agents

    # ─────────────────────────────────────────────────────────────────────────
    # Phase 1: Generate Strategic ContentBrief
    # ─────────────────────────────────────────────────────────────────────────

    def generate_content_brief(
        self,
        brand_id: str,
        brand_memory: Dict[str, Any],
        existing_topic: Optional[str] = None,
    ) -> ContentBrief:
        """
        Generates a structured ContentBrief for the specialist agent.
        Pulls from strategic memory, audience intelligence, and trend opportunities.
        Preserves brand identity — does NOT contaminate channel editorial rules.
        """
        brand_profile = get_brand_config(brand_id)
        channel_context = self.strategic_memory.get_channel_context_for_brief(brand_id)
        geo_brief = AudienceIntelligence.get_geographic_briefing(brand_id, DEFAULT_TARGET_GEOGRAPHY)

        # Determine portfolio category from historical performance
        historical = self.strategic_memory.get_channel_memory(brand_id)
        category_decision = self.strategy_engine.select_portfolio_category(brand_id, {
            "recent_winners": historical.get("winners", []),
            "recent_failures": historical.get("failures", []),
        })
        portfolio_cat = PortfolioCategory(category_decision["category"].value)

        # Discover trend opportunities for topic direction
        opportunities = self.trend_intel.discover_opportunities(brand_id, brand_profile, brand_memory)
        top_opportunity = opportunities[0] if opportunities else {}

        # If a pre-determined topic was passed (from Firestore), use it
        topic = existing_topic or top_opportunity.get("topic", "")
        hook_direction = top_opportunity.get("hook_direction", "")

        # Strategic reasoning for the brief via LLM
        strategic_brief_data = self._generate_strategic_brief_via_llm(
            brand_id, brand_profile, channel_context, geo_brief, topic, hook_direction, portfolio_cat
        )

        brief = ContentBrief(
            request_id=f"atlas_{uuid.uuid4().hex[:8]}",
            channel=brand_id,
            target_audience=", ".join(geo_brief.get("target_segments", [])),
            target_geography=DEFAULT_TARGET_GEOGRAPHY,
            content_pillar=brand_profile.get("categories", ["General"])[0],
            portfolio_category=portfolio_cat,
            objective=strategic_brief_data.get("objective", "Drive high-engagement content"),
            topic=topic,
            core_insight=strategic_brief_data.get("core_insight", ""),
            hook_direction=hook_direction,
            emotional_trigger=top_opportunity.get("emotional_trigger", "curiosity"),
            narrative_structure=strategic_brief_data.get("narrative_structure", "Hook → Insight → Application → CTA"),
            expected_length=brand_profile.get("preferred_video_duration", 30),
            visual_direction=brand_profile.get("visual_style", ""),
            tone=brand_profile.get("tone", ""),
            cta_strategy=brand_profile.get("cta", ""),
            title_direction=strategic_brief_data.get("title_direction", ""),
            discovery_terms=geo_brief.get("terminology", []),
            brand_restrictions=brand_profile.get("avoid_topics", []),
            priority=brand_profile.get("priority", "medium"),
        )

        logger.info(
            f"ATLAS ContentBrief generated: brand={brand_id}, topic='{topic}', "
            f"category={portfolio_cat.value}, mode={'SHADOW' if ATLAS_SHADOW_MODE else 'ACTIVE'}"
        )
        return brief

    def _generate_strategic_brief_via_llm(
        self, brand_id, brand_profile, channel_context, geo_brief, topic, hook_direction, portfolio_cat
    ) -> Dict[str, Any]:
        recent_winning_mechanisms = channel_context.get("recent_winning_mechanisms", [])
        failure_types = channel_context.get("recent_failure_types", [])

        prompt = f"""
You are ATLAS, the strategic intelligence layer for the '{brand_profile.get('display_name', brand_id)}' channel.
Portfolio Category: {portfolio_cat.value}
Topic: {topic}
Hook Direction: {hook_direction}
Target Geography: {geo_brief.get('target_geography')}
Target Audience Segments: {geo_brief.get('target_segments')}
US-Relevant Terminology: {geo_brief.get('terminology')}
Recent Winning Mechanisms: {recent_winning_mechanisms}
Recent Failure Patterns: {failure_types}

Generate a precise strategic execution brief. Return JSON:
{{
    "objective": "Single clear intent for this content piece",
    "core_insight": "Central insight that makes this video worth watching",
    "narrative_structure": "Hook → [steps]",
    "title_direction": "Compelling title angle (do not write the final title)"
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
            return json.loads(res.text)
        except Exception as e:
            logger.warning(f"Strategic brief LLM call failed: {e}. Using defaults.")
            return {
                "objective": "Deliver high-value, engaging content aligned with brand identity.",
                "core_insight": "Practical insight that changes how the audience thinks or acts.",
                "narrative_structure": "Hook → Core Insight → Evidence → Application → CTA",
                "title_direction": "Direct, curiosity-driving headline"
            }

    # ─────────────────────────────────────────────────────────────────────────
    # Phase 2: Route Brief to Specialist Agent
    # ─────────────────────────────────────────────────────────────────────────

    def route_brief_to_specialist(
        self, brand_id: str, brief: ContentBrief, brand_memory: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Routes the ContentBrief to the correct specialist agent.
        Uses invoke_agent_with_brief() which passes brief context while
        preserving the specialist's system prompt and brand identity.
        """
        from src.agents.google_agent_client import GoogleAgentClient
        from google.cloud import firestore
        db = firestore.Client()

        brand_profile_doc = db.collection("brands").document(brand_id).get()
        brand_profile = brand_profile_doc.to_dict() if brand_profile_doc.exists else get_brand_config(brand_id)

        client = GoogleAgentClient()
        output = client.invoke_agent_with_brief(brand_id, brand_profile, brand_memory, brief)

        logger.info(f"Specialist '{brand_id}' responded: topic='{output.get('topic')}', confidence={output.get('confidence')}")
        return output

    # ─────────────────────────────────────────────────────────────────────────
    # Phase 3: QA Governance Evaluation
    # ─────────────────────────────────────────────────────────────────────────

    def evaluate_specialist_output(
        self, brand_id: str, brief: ContentBrief, specialist_output: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        ATLAS QA Governance evaluates specialist output.
        In Shadow Mode: logs the evaluation but always returns PASS.
        In Active Mode: returns REVISE or REJECT to block content.
        """
        from google.cloud import firestore
        db = firestore.Client()
        brand_profile_doc = db.collection("brands").document(brand_id).get()
        brand_profile = brand_profile_doc.to_dict() if brand_profile_doc.exists else get_brand_config(brand_id)

        evaluation = self.qa_engine.evaluate_content(brand_profile, brief.to_dict(), specialist_output)

        if ATLAS_SHADOW_MODE:
            logger.info(
                f"[ATLAS SHADOW QA] brand={brand_id}, result={evaluation.result.value}, "
                f"score={evaluation.score:.2f}. Shadow mode: bypassing gate."
            )
            return {"qa_passed": True, "shadow_evaluation": evaluation.to_dict()}

        if evaluation.result == QAResult.REJECT:
            logger.warning(f"[ATLAS QA REJECT] brand={brand_id}: {evaluation.feedback}")
            return {"qa_passed": False, "evaluation": evaluation.to_dict()}
        elif evaluation.result == QAResult.REVISE:
            logger.info(f"[ATLAS QA REVISE] brand={brand_id}: {evaluation.revision_instructions}")
            return {"qa_passed": False, "evaluation": evaluation.to_dict()}

        return {"qa_passed": True, "evaluation": evaluation.to_dict()}

    # ─────────────────────────────────────────────────────────────────────────
    # Phase 4: Post-Publish Learning Loop
    # ─────────────────────────────────────────────────────────────────────────

    def ingest_and_learn(
        self, brand_id: str, content_id: str, content_item: Dict[str, Any], performance_metrics: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Called after a video has been published and analytics data is available.
        1. Records performance in atlas_performance_records.
        2. Runs learning engine to derive root-cause mechanism.
        3. Updates strategic memory.
        """
        video_id = content_item.get("youtube_video_id", "")
        perf_record = self.performance_intel.record_item_performance(
            content_id, brand_id, video_id, performance_metrics
        )

        history = self.performance_intel.get_brand_performance_history(brand_id, limit=20)
        avg_views = (
            sum(r.get("views", 0) for r in history) / len(history)
            if history else 1
        )
        baseline = {"avg_views": avg_views}

        insight = self.learning_engine.analyze_item_performance(
            brand_id, content_item, perf_record, baseline
        )

        if perf_record.get("views", 0) > avg_views * 1.5:
            self.strategic_memory.record_winner(brand_id, content_id, insight)
        elif insight.failure_type:
            self.strategic_memory.record_failure(brand_id, content_id, insight)

        result = {
            "content_id": content_id,
            "brand_id": brand_id,
            "insight": insight.to_dict(),
            "performance_summary": perf_record,
        }
        logger.info(
            f"[ATLAS LEARNING] brand={brand_id}, content_id={content_id}, "
            f"mechanism='{insight.underlying_mechanism[:80]}'"
        )
        return result
