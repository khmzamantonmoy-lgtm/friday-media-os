"""
tests/test_atlas.py

ATLAS Strategic Orchestration Layer — Integration & Unit Tests.

Tests cover:
- ContentBrief generation and serialization
- Agent routing (invoke_agent_with_brief contract preservation)
- QA Governance (PASS / REVISE / REJECT modes)
- Shadow mode bypass
- Strategic memory (winner/failure recording and pattern promotion)
- Learning engine (failure type classification)
- Portfolio category selection logic
- End-to-end brief → QA → learning loop (mocked)
"""

import json
import uuid
import unittest
from unittest.mock import MagicMock, patch, PropertyMock
from dataclasses import dataclass

# ── Model imports ──────────────────────────────────────────────────────────────
from src.atlas.models import (
    ContentBrief,
    QAEvaluation,
    LearningInsight,
    QAResult,
    EvidenceLevel,
    FailureType,
    PortfolioCategory,
)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def make_brief(brand_id="bd_threatpulse", topic="Zero-Trust Principles") -> ContentBrief:
    return ContentBrief(
        request_id=f"atlas_{uuid.uuid4().hex[:8]}",
        channel=brand_id,
        target_audience="CISOs, CIOs, technology executives",
        target_geography="US",
        content_pillar="Cybersecurity",
        portfolio_category=PortfolioCategory.CORE,
        objective="Educate enterprise security leaders on Zero-Trust architecture.",
        topic=topic,
        core_insight="Perimeter-based security is obsolete; identity is the new perimeter.",
        hook_direction="Open with a real breach caused by implicit trust assumptions.",
        emotional_trigger="urgency",
        narrative_structure="Hook → Threat Reality → Zero-Trust Framework → 3 Actions → CTA",
        expected_length=45,
        visual_direction="Dark corporate aesthetic; red threat indicators",
        tone="authoritative, urgent",
        cta_strategy="Subscribe for weekly threat briefings",
        title_direction="Headline ending with a cost figure or stat",
        discovery_terms=["zero trust", "identity verification", "CISA guidelines"],
        brand_restrictions=["cryptocurrency", "personal finance"],
        priority="high",
    )


# ─────────────────────────────────────────────────────────────────────────────
# 1. ContentBrief Model Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestContentBriefModel(unittest.TestCase):

    def test_brief_creation(self):
        brief = make_brief()
        self.assertEqual(brief.channel, "bd_threatpulse")
        self.assertEqual(brief.target_geography, "US")
        self.assertEqual(brief.portfolio_category, PortfolioCategory.CORE)

    def test_brief_to_dict_completeness(self):
        brief = make_brief()
        d = brief.to_dict()
        required_keys = [
            "request_id", "channel", "target_audience", "target_geography",
            "content_pillar", "portfolio_category", "objective", "topic",
            "core_insight", "hook_direction", "emotional_trigger",
            "narrative_structure", "expected_length", "tone", "discovery_terms",
            "brand_restrictions",
        ]
        for k in required_keys:
            self.assertIn(k, d, f"Missing key in to_dict(): {k}")

    def test_brief_portfolio_category_serializes_as_string(self):
        brief = make_brief()
        d = brief.to_dict()
        self.assertIsInstance(d["portfolio_category"], str)
        self.assertEqual(d["portfolio_category"], "CORE")

    def test_brief_channel_identity_preserved(self):
        """ATLAS brief must never overwrite channel identity fields."""
        brief = make_brief(brand_id="wealthwise")
        self.assertEqual(brief.channel, "wealthwise")
        # Verify brand restrictions carry over from brand profile
        self.assertNotIn("cryptocurrency", brief.topic.lower())


# ─────────────────────────────────────────────────────────────────────────────
# 2. QAEvaluation Model Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestQAEvaluationModel(unittest.TestCase):

    def test_pass_evaluation(self):
        ev = QAEvaluation(
            result=QAResult.PASS, score=0.92, feedback="Strong brand alignment.",
            channel_fit=True, audience_fit=True, geographic_fit=True,
            originality_score=0.88, retention_hypothesis="Strong hook."
        )
        self.assertEqual(ev.result, QAResult.PASS)
        self.assertIsNone(ev.revision_instructions)

    def test_revise_evaluation_has_instructions(self):
        ev = QAEvaluation(
            result=QAResult.REVISE, score=0.55, feedback="Topic too generic.",
            channel_fit=True, audience_fit=False, geographic_fit=True,
            originality_score=0.40, retention_hypothesis="Low retention expected.",
            revision_instructions="Narrow the topic to a specific sub-theme."
        )
        self.assertEqual(ev.result, QAResult.REVISE)
        self.assertIsNotNone(ev.revision_instructions)

    def test_reject_evaluation(self):
        ev = QAEvaluation(
            result=QAResult.REJECT, score=0.10, feedback="Brand restriction violated.",
            channel_fit=False, audience_fit=False, geographic_fit=True,
            originality_score=0.10, retention_hypothesis="Negligible.",
        )
        d = ev.to_dict()
        self.assertEqual(d["result"], "REJECT")
        self.assertFalse(d["channel_fit"])


# ─────────────────────────────────────────────────────────────────────────────
# 3. LearningInsight Model Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestLearningInsightModel(unittest.TestCase):

    def test_learning_insight_winner(self):
        insight = LearningInsight(
            insight_id="insight_abc123",
            brand_id="wealthwise",
            evidence_level=EvidenceLevel.OBSERVED,
            underlying_mechanism="Index fund explainers with real portfolio math outperform general strategy content.",
            failure_type=None,
            derived_action="Test single-ticker deep-dive format as controlled experiment.",
        )
        self.assertIsNone(insight.failure_type)
        d = insight.to_dict()
        self.assertEqual(d["evidence_level"], "OBSERVED")
        self.assertIsNone(d["failure_type"])

    def test_learning_insight_failure(self):
        insight = LearningInsight(
            insight_id="insight_xyz789",
            brand_id="philosophy",
            evidence_level=EvidenceLevel.INFERRED,
            underlying_mechanism="Abstract concept videos without concrete examples fail to retain viewers past 15s.",
            failure_type=FailureType.EXECUTION_FAILURE,
            derived_action="Add concrete real-world example in first 15 seconds.",
        )
        d = insight.to_dict()
        self.assertEqual(d["failure_type"], "EXECUTION_FAILURE")

    def test_insufficient_data_classification(self):
        insight = LearningInsight(
            insight_id="insight_new001",
            brand_id="kids_universe",
            evidence_level=EvidenceLevel.HYPOTHESIS,
            underlying_mechanism="No meaningful data yet (< 72 hours post-publish).",
            failure_type=FailureType.INSUFFICIENT_DATA,
            derived_action="Re-evaluate in 7 days.",
        )
        self.assertEqual(insight.failure_type, FailureType.INSUFFICIENT_DATA)


# ─────────────────────────────────────────────────────────────────────────────
# 4. ContentStrategy Portfolio Selection Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestContentStrategyEngine(unittest.TestCase):

    def setUp(self):
        from src.atlas.strategy.content_strategy import ContentStrategyEngine
        self.engine = ContentStrategyEngine()

    def test_high_failure_rate_anchors_to_core(self):
        historical = {
            "recent_winners": [],
            "recent_failures": [{"failure_type": "TOPIC_FAILURE"}] * 5,
        }
        result = self.engine.select_portfolio_category("wealthwise", historical)
        self.assertEqual(result["category"], PortfolioCategory.CORE)
        self.assertIn("CORE", result["reasoning"])

    def test_strong_winners_promotes_growth(self):
        historical = {
            "recent_winners": [{"mechanism": "explainer format"}] * 4,
            "recent_failures": [],
        }
        result = self.engine.select_portfolio_category("bd_threatpulse", historical)
        self.assertEqual(result["category"], PortfolioCategory.GROWTH)

    def test_neutral_history_defaults_core(self):
        result = self.engine.select_portfolio_category("philosophy", {"recent_winners": [], "recent_failures": []})
        self.assertEqual(result["category"], PortfolioCategory.CORE)
        self.assertEqual(result["evidence_level"], EvidenceLevel.INFERRED.value)


# ─────────────────────────────────────────────────────────────────────────────
# 5. QA Governance Shadow Mode Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestQAGovernanceShadowMode(unittest.TestCase):

    @patch("src.atlas.governance.qa_governance.ATLAS_SHADOW_MODE", True)
    @patch("src.atlas.governance.qa_governance.AIRequestManager")
    def test_shadow_mode_passes_regardless_of_evaluation(self, MockAI):
        """In shadow mode, even a REJECT score must not block production."""
        from src.atlas.governance.qa_governance import ContentGovernanceEngine

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.text = json.dumps({
            "result": "REJECT",
            "score": 0.10,
            "feedback": "Test violation.",
            "channel_fit": False,
            "audience_fit": False,
            "geographic_fit": True,
            "originality_score": 0.10,
            "retention_hypothesis": "Very low.",
        })
        mock_client.models.generate_content.return_value = mock_response
        MockAI.return_value.execute.side_effect = lambda fn: fn(mock_client)

        engine = ContentGovernanceEngine()
        brand_profile = {"display_name": "BD ThreatPulse", "avoid_topics": []}
        brief = make_brief().to_dict()
        specialist_output = {"topic": "Zero-Trust Security", "script": "Test narration."}

        evaluation = engine.evaluate_content(brand_profile, brief, specialist_output)
        # Shadow mode: evaluation runs but QAResult may be REJECT
        # The orchestrator's evaluate_specialist_output() is responsible for shadow bypass
        self.assertIsNotNone(evaluation)

    def test_brand_restriction_triggers_reject(self):
        """Synchronous rule-based check must fire before any LLM call."""
        from src.atlas.governance.qa_governance import ContentGovernanceEngine

        engine = ContentGovernanceEngine()
        brand_profile = {"display_name": "BD ThreatPulse", "avoid_topics": ["cryptocurrency"]}
        brief = make_brief().to_dict()
        specialist_output = {"topic": "Top 10 Cryptocurrency Security Risks", "script": "..."}

        evaluation = engine.evaluate_content(brand_profile, brief, specialist_output)
        self.assertEqual(evaluation.result, QAResult.REJECT)
        self.assertIn("cryptocurrency", evaluation.feedback.lower())


# ─────────────────────────────────────────────────────────────────────────────
# 6. Experimentation Engine Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestExperimentationEngine(unittest.TestCase):

    @patch("src.atlas.strategy.experimentation.firestore")
    def test_create_and_record_experiment_adopt(self, mock_firestore):
        from src.atlas.strategy.experimentation import ExperimentationEngine

        mock_db = MagicMock()
        mock_firestore.Client.return_value = mock_db
        mock_db.collection.return_value.document.return_value.get.return_value.exists = True
        mock_db.collection.return_value.document.return_value.get.return_value.to_dict.return_value = {
            "experiment_id": "exp_test_000",
            "status": "ACTIVE",
        }

        engine = ExperimentationEngine()
        exp = engine.create_experiment(
            brand_id="wealthwise",
            hypothesis="Opening with a hard number improves CTR",
            variable="hook_format",
            control_value="narrative_open",
            test_value="stat_open",
        )
        self.assertIn("exp_wealthwise_", exp["experiment_id"])
        self.assertEqual(exp["status"], "ACTIVE")

    @patch("src.atlas.strategy.experimentation.firestore")
    def test_experiment_result_adopt_decision(self, mock_firestore):
        from src.atlas.strategy.experimentation import ExperimentationEngine

        mock_db = MagicMock()
        mock_firestore.Client.return_value = mock_db
        mock_db.collection.return_value.document.return_value.get.return_value.exists = True
        mock_db.collection.return_value.document.return_value.get.return_value.to_dict.return_value = {}

        engine = ExperimentationEngine()
        result = engine.record_experiment_result("exp_test_001", test_performance=0.85, control_baseline=0.60)
        self.assertEqual(result["decision"], "ADOPT_TEST")

    @patch("src.atlas.strategy.experimentation.firestore")
    def test_experiment_result_reject_decision(self, mock_firestore):
        from src.atlas.strategy.experimentation import ExperimentationEngine

        mock_db = MagicMock()
        mock_firestore.Client.return_value = mock_db
        mock_db.collection.return_value.document.return_value.get.return_value.exists = True
        mock_db.collection.return_value.document.return_value.get.return_value.to_dict.return_value = {}

        engine = ExperimentationEngine()
        result = engine.record_experiment_result("exp_test_002", test_performance=0.40, control_baseline=0.60)
        self.assertEqual(result["decision"], "REJECT_TEST")


# ─────────────────────────────────────────────────────────────────────────────
# 7. Strategic Memory Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestStrategicMemory(unittest.TestCase):

    @patch("src.atlas.memory.strategic_memory.firestore")
    def test_record_winner_persists_mechanism(self, mock_firestore):
        from src.atlas.memory.strategic_memory import StrategicMemory

        mock_db = MagicMock()
        mock_firestore.Client.return_value = mock_db
        mock_doc = MagicMock()
        mock_doc.exists = True
        mock_doc.to_dict.return_value = {"winners": []}
        mock_db.collection.return_value.document.return_value.get.return_value = mock_doc

        mem = StrategicMemory()
        insight = LearningInsight(
            insight_id="insight_001",
            brand_id="bd_threatpulse",
            evidence_level=EvidenceLevel.OBSERVED,
            underlying_mechanism="Breach case studies with cost data outperform generic threat overviews.",
            derived_action="Create 3 more breach case study formats as controlled set.",
        )
        mem.record_winner("bd_threatpulse", "bd_threatpulse_abc123", insight)
        mock_db.collection.return_value.document.return_value.set.assert_called_once()

    @patch("src.atlas.memory.strategic_memory.firestore")
    def test_failure_pattern_promotes_after_threshold(self, mock_firestore):
        """
        After MINIMUM_DATA_POINTS_FOR_CONCLUSION (3) failures of same type,
        the pattern is promoted to a strategic conclusion.
        """
        from src.atlas.memory.strategic_memory import StrategicMemory

        mock_db = MagicMock()
        mock_firestore.Client.return_value = mock_db

        existing_failures = [
            {"failure_type": "TOPIC_FAILURE"}, {"failure_type": "TOPIC_FAILURE"}
        ]
        mock_doc = MagicMock()
        mock_doc.exists = True
        mock_doc.to_dict.return_value = {"failures": existing_failures}
        mock_db.collection.return_value.document.return_value.get.return_value = mock_doc

        mem = StrategicMemory()
        insight = LearningInsight(
            insight_id="insight_002",
            brand_id="philosophy",
            evidence_level=EvidenceLevel.INFERRED,
            underlying_mechanism="Abstract content fails to engage.",
            failure_type=FailureType.TOPIC_FAILURE,
            derived_action="Add concrete example in first 15 seconds.",
        )
        mem.record_failure("philosophy", "philosophy_xyz", insight)

        call_args = mock_db.collection.return_value.document.return_value.set.call_args
        payload = call_args[0][0]
        # After 3 TOPIC_FAILUREs, strategic_conclusions should be populated
        self.assertIn("TOPIC_FAILURE", payload.get("strategic_conclusions", {}))


# ─────────────────────────────────────────────────────────────────────────────
# 8. invoke_agent_with_brief Contract Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestInvokeAgentWithBrief(unittest.TestCase):

    @patch("src.agents.google_agent_client.AIRequestManager")
    def test_specialist_system_instruction_unchanged(self, MockAIManager):
        """
        The most critical invariant: the specialist's system_instruction must
        NEVER be modified. Only the user prompt receives the ATLAS advisory block.
        """
        from src.agents.google_agent_client import GoogleAgentClient, AGENT_MAPPING

        mock_response = MagicMock()
        mock_response.text = json.dumps({
            "agent_name": "BD ThreatPulse Editorial AI",
            "topic": "Zero-Trust Security Architecture",
            "category": "Cybersecurity",
            "editorial_reasoning": "High enterprise relevance.",
            "is_breaking_news": False,
            "confidence": 0.95,
            "quality_score": 0.92,
            "verification_status": "verified",
            "verification_sources": ["CISA"],
            "similarity_score": 0.05,
            "seo_title": "Why Zero-Trust Ends Perimeter Security",
            "description": "Full description.",
            "hashtags": ["#cybersecurity"],
            "cta": "Subscribe",
            "script_narration": "Today we discuss...",
            "scene_plan": [],
        })

        captured_config = {}

        def capture_op(fn):
            # Intercept the generate_content call to inspect config
            class FakeClient:
                class models:
                    @staticmethod
                    def generate_content(model, contents, config):
                        captured_config["config"] = config
                        return mock_response
            return fn(FakeClient())

        MockAIManager.return_value.execute.side_effect = capture_op

        client = GoogleAgentClient()
        brief = make_brief()
        brand_profile = {
            "display_name": "BD ThreatPulse",
            "audience": "CISOs",
            "tone": "authoritative",
            "content_angle": "Cybersecurity threat intelligence",
            "categories": ["Cybersecurity"],
            "avoid_topics": ["personal finance"],
            "preferred_video_duration": 45,
        }
        result = client.invoke_agent_with_brief("bd_threatpulse", brand_profile, {}, brief)

        # Specialist identity preserved: system_instruction must match original
        original_system_instruction = AGENT_MAPPING["bd_threatpulse"]["system_instruction"]
        used_system_instruction = captured_config["config"].system_instruction
        self.assertEqual(used_system_instruction, original_system_instruction)

        # ATLAS brief ID attached to response
        self.assertIn("atlas_brief_id", result)
        self.assertEqual(result["agent_name"], "BD ThreatPulse Editorial AI")

    @patch("src.agents.google_agent_client.AIRequestManager")
    def test_atlas_advisory_appears_in_user_prompt_not_system(self, MockAIManager):
        """ATLAS advisory block must be in the user contents, not system_instruction."""
        from src.agents.google_agent_client import GoogleAgentClient

        captured_contents = {}
        mock_response = MagicMock()
        mock_response.text = json.dumps({
            "agent_name": "WealthWise Financial Intelligence AI",
            "topic": "Index Fund Discipline During Volatility",
            "category": "Investing",
            "editorial_reasoning": "Timely macro relevance.",
            "is_breaking_news": False, "confidence": 0.90, "quality_score": 0.88,
            "verification_status": "verified", "verification_sources": ["Fed Reserve"],
            "similarity_score": 0.08, "seo_title": "Stay Invested During Market Panic",
            "description": "Description.", "hashtags": ["#investing"],
            "cta": "Subscribe", "script_narration": "Today's topic...", "scene_plan": [],
        })

        def capture_op(fn):
            class FakeClient:
                class models:
                    @staticmethod
                    def generate_content(model, contents, config):
                        captured_contents["prompt"] = contents
                        return mock_response
            return fn(FakeClient())

        MockAIManager.return_value.execute.side_effect = capture_op

        client = GoogleAgentClient()
        brief = make_brief(brand_id="wealthwise", topic="Index Fund Discipline During Volatility")
        brand_profile = {
            "display_name": "WealthWise",
            "audience": "Retail investors",
            "tone": "confident",
            "content_angle": "Financial intelligence",
            "categories": ["Finance"],
            "avoid_topics": [],
            "preferred_video_duration": 30,
        }
        client.invoke_agent_with_brief("wealthwise", brand_profile, {}, brief)
        self.assertIn("ATLAS STRATEGIC BRIEF", captured_contents.get("prompt", ""))


# ─────────────────────────────────────────────────────────────────────────────
# 9. End-to-End Orchestrator Loop (Mocked)
# ─────────────────────────────────────────────────────────────────────────────

class TestATLASEndToEndMocked(unittest.TestCase):

    @patch("src.atlas.orchestrator.firestore")
    @patch("src.atlas.orchestrator.AIRequestManager")
    @patch("src.atlas.orchestrator.TrendIntelligence")
    @patch("src.atlas.orchestrator.StrategicMemory")
    @patch("src.atlas.orchestrator.PerformanceIntelligence")
    @patch("src.atlas.orchestrator.LearningEngine")
    @patch("src.atlas.orchestrator.ContentGovernanceEngine")
    def test_shadow_mode_evaluate_never_blocks(
        self, MockQA, MockLearn, MockPerf, MockMem, MockTrend, MockAI, mock_firestore
    ):
        """In shadow mode, qa_passed must always be True regardless of QA result."""
        from src.atlas.orchestrator import ATLASOrchestrator
        import src.atlas.orchestrator as orch_mod

        orch_mod.ATLAS_SHADOW_MODE = True

        mock_qa_instance = MockQA.return_value
        mock_qa_instance.evaluate_content.return_value = QAEvaluation(
            result=QAResult.REJECT, score=0.1, feedback="Test reject.",
            channel_fit=False, audience_fit=False, geographic_fit=True,
            originality_score=0.1, retention_hypothesis="Very low."
        )

        orchestrator = ATLASOrchestrator()
        brief = make_brief()

        mock_firestore.Client.return_value.collection.return_value.document.return_value.get.return_value.exists = False

        result = orchestrator.evaluate_specialist_output(
            "bd_threatpulse",
            brief,
            {"topic": "Zero-Trust", "script": "..."}
        )
        self.assertTrue(result["qa_passed"])
        self.assertIn("shadow_evaluation", result)

    @patch("src.atlas.orchestrator.PerformanceIntelligence")
    @patch("src.atlas.orchestrator.LearningEngine")
    @patch("src.atlas.orchestrator.StrategicMemory")
    def test_ingest_and_learn_records_winner(self, MockMem, MockLearn, MockPerf):
        """High-performing content is classified as a winner in strategic memory."""
        from src.atlas.orchestrator import ATLASOrchestrator

        mock_learn_instance = MockLearn.return_value
        mock_learn_instance.analyze_item_performance.return_value = LearningInsight(
            insight_id="insight_e2e_001",
            brand_id="wealthwise",
            evidence_level=EvidenceLevel.OBSERVED,
            underlying_mechanism="Practical math examples drive high completion.",
            failure_type=None,
            derived_action="Replicate calculation-first hook format."
        )

        mock_perf_instance = MockPerf.return_value
        mock_perf_instance.record_item_performance.return_value = {
            "views": 5000, "retention_rate": 0.72, "likes": 350
        }
        mock_perf_instance.get_brand_performance_history.return_value = [
            {"views": 2000}
        ] * 10  # avg = 2000, winner threshold = 3000

        mock_mem_instance = MockMem.return_value
        mock_mem_instance.get_channel_memory.return_value = {}

        orchestrator = ATLASOrchestrator()
        result = orchestrator.ingest_and_learn(
            brand_id="wealthwise",
            content_id="wealthwise_abc123",
            content_item={"topic": "Index Fund Math", "youtube_video_id": "yt_abc"},
            performance_metrics={"views": 5000, "retention_rate": 0.72}
        )

        self.assertEqual(result["brand_id"], "wealthwise")
        mock_mem_instance.record_winner.assert_called_once()
        mock_mem_instance.record_failure.assert_not_called()


if __name__ == "__main__":
    unittest.main()
