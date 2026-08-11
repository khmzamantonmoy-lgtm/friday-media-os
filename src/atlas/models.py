"""
models.py

Structured Agent Contract and Data Models for ATLAS
(Audience, Trend & Learning Adaptive Strategy Orchestrator).
"""

from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from enum import Enum
import datetime


class EvidenceLevel(str, Enum):
    OBSERVED = "OBSERVED"
    INFERRED = "INFERRED"
    HYPOTHESIS = "HYPOTHESIS"


class FailureType(str, Enum):
    TOPIC_FAILURE = "TOPIC_FAILURE"
    EXECUTION_FAILURE = "EXECUTION_FAILURE"
    PACKAGING_FAILURE = "PACKAGING_FAILURE"
    AUDIENCE_FAILURE = "AUDIENCE_FAILURE"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class QAResult(str, Enum):
    PASS = "PASS"
    REVISE = "REVISE"
    REJECT = "REJECT"


class PortfolioCategory(str, Enum):
    CORE = "CORE"
    GROWTH = "GROWTH"
    AUTHORITY = "AUTHORITY"
    EXPERIMENTAL = "EXPERIMENTAL"
    SEASONAL = "SEASONAL"
    TREND_RESPONSIVE = "TREND_RESPONSIVE"
    EVERGREEN = "EVERGREEN"


@dataclass
class ContentBrief:
    request_id: str
    channel: str
    target_audience: str
    target_geography: str = "US"
    content_pillar: str = "General"
    portfolio_category: PortfolioCategory = PortfolioCategory.CORE
    objective: str = ""
    topic: str = ""
    core_insight: str = ""
    hook_direction: str = ""
    emotional_trigger: str = ""
    narrative_structure: str = ""
    expected_length: int = 30
    visual_direction: str = ""
    tone: str = ""
    cta_strategy: str = ""
    title_direction: str = ""
    discovery_terms: List[str] = field(default_factory=list)
    factual_requirements: List[str] = field(default_factory=list)
    brand_restrictions: List[str] = field(default_factory=list)
    experiment_id: Optional[str] = None
    priority: str = "medium"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "request_id": self.request_id,
            "channel": self.channel,
            "target_audience": self.target_audience,
            "target_geography": self.target_geography,
            "content_pillar": self.content_pillar,
            "portfolio_category": self.portfolio_category.value,
            "objective": self.objective,
            "topic": self.topic,
            "core_insight": self.core_insight,
            "hook_direction": self.hook_direction,
            "emotional_trigger": self.emotional_trigger,
            "narrative_structure": self.narrative_structure,
            "expected_length": self.expected_length,
            "visual_direction": self.visual_direction,
            "tone": self.tone,
            "cta_strategy": self.cta_strategy,
            "title_direction": self.title_direction,
            "discovery_terms": self.discovery_terms,
            "factual_requirements": self.factual_requirements,
            "brand_restrictions": self.brand_restrictions,
            "experiment_id": self.experiment_id,
            "priority": self.priority,
        }


@dataclass
class QAEvaluation:
    result: QAResult
    score: float
    feedback: str
    channel_fit: bool
    audience_fit: bool
    geographic_fit: bool
    originality_score: float
    retention_hypothesis: str
    revision_instructions: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "result": self.result.value,
            "score": self.score,
            "feedback": self.feedback,
            "channel_fit": self.channel_fit,
            "audience_fit": self.audience_fit,
            "geographic_fit": self.geographic_fit,
            "originality_score": self.originality_score,
            "retention_hypothesis": self.retention_hypothesis,
            "revision_instructions": self.revision_instructions,
        }


@dataclass
class LearningInsight:
    insight_id: str
    brand_id: str
    evidence_level: EvidenceLevel
    underlying_mechanism: str
    failure_type: Optional[FailureType] = None
    derived_action: str = ""
    created_at: str = field(default_factory=lambda: datetime.datetime.utcnow().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "insight_id": self.insight_id,
            "brand_id": self.brand_id,
            "evidence_level": self.evidence_level.value,
            "underlying_mechanism": self.underlying_mechanism,
            "failure_type": self.failure_type.value if self.failure_type else None,
            "derived_action": self.derived_action,
            "created_at": self.created_at,
        }
