"""
verification_layer.py

Pre-pipeline quality and safety verification layer for FRIDAY Media OS.
Validates agent editorial packages for similarity, confidence, verification sources,
and quality scores before allowing downstream media rendering.
"""

import logging
from dataclasses import dataclass

logger = logging.getLogger("verification_layer")


@dataclass
class VerificationResult:
    passed: bool
    status: str  # "VERIFIED", "REJECTED_SIMILARITY", "REJECTED_CONFIDENCE", "REJECTED_QUALITY", "REJECTED_SOURCES"
    reason: str
    metrics: dict


class VerificationLayer:
    def __init__(self, default_max_similarity: float = 0.80, default_min_confidence: float = 0.70, default_min_quality: float = 0.75):
        self.default_max_similarity = default_max_similarity
        self.default_min_confidence = default_min_confidence
        self.default_min_quality = default_min_quality

    def verify_decision(
        self,
        agent_package: dict,
        brand_profile: dict,
        brand_memory: dict,
    ) -> VerificationResult:
        """
        Runs comprehensive verification on an agent editorial decision package.
        Returns VerificationResult.
        """
        topic = agent_package.get("topic", "")
        max_sim_threshold = brand_profile.get("never_repeat_similarity", self.default_max_similarity)
        confidence = float(agent_package.get("confidence", 0.0))
        quality = float(agent_package.get("quality_score", 0.0))
        sources = agent_package.get("verification_sources", [])
        is_breaking = agent_package.get("is_breaking_news", False)

        # 1. Similarity Check against recent topics & titles
        recent_topics = brand_memory.get("recent_topics", [])
        recent_titles = brand_memory.get("recent_titles", [])
        calculated_similarity = self._compute_similarity(topic, recent_topics + recent_titles)

        # Override package similarity if calculated is higher
        pkg_similarity = float(agent_package.get("similarity_score", 0.0))
        effective_similarity = max(pkg_similarity, calculated_similarity)

        metrics = {
            "effective_similarity": round(effective_similarity, 3),
            "max_allowed_similarity": max_sim_threshold,
            "confidence": round(confidence, 3),
            "min_required_confidence": self.default_min_confidence,
            "quality_score": round(quality, 3),
            "min_required_quality": self.default_min_quality,
            "source_count": len(sources),
        }

        # Check 1: Similarity Threshold
        if effective_similarity >= max_sim_threshold:
            reason = f"Topic '{topic}' similarity ({effective_similarity:.2f}) exceeds threshold ({max_sim_threshold:.2f})"
            logger.warning(f"Verification Failed: {reason}")
            return VerificationResult(
                passed=False,
                status="REJECTED_SIMILARITY",
                reason=reason,
                metrics=metrics,
            )

        # Check 2: Confidence Threshold
        if confidence < self.default_min_confidence:
            reason = f"Agent confidence ({confidence:.2f}) below required minimum ({self.default_min_confidence:.2f})"
            logger.warning(f"Verification Failed: {reason}")
            return VerificationResult(
                passed=False,
                status="REJECTED_CONFIDENCE",
                reason=reason,
                metrics=metrics,
            )

        # Check 3: Quality Threshold
        if quality < self.default_min_quality:
            reason = f"Agent quality score ({quality:.2f}) below required minimum ({self.default_min_quality:.2f})"
            logger.warning(f"Verification Failed: {reason}")
            return VerificationResult(
                passed=False,
                status="REJECTED_QUALITY",
                reason=reason,
                metrics=metrics,
            )

        # Check 4: Source Verification for Breaking News
        if is_breaking and not sources:
            reason = "Breaking news package requires at least 1 verified source."
            logger.warning(f"Verification Failed: {reason}")
            return VerificationResult(
                passed=False,
                status="REJECTED_SOURCES",
                reason=reason,
                metrics=metrics,
            )

        # All checks passed
        logger.info(f"Verification Passed for topic '{topic}' (Quality: {quality:.2f}, Confidence: {confidence:.2f})")
        return VerificationResult(
            passed=True,
            status="VERIFIED",
            reason="All quality, safety, and non-repetition thresholds passed.",
            metrics=metrics,
        )

    def _compute_similarity(self, target: str, history: list[str]) -> float:
        """Computes Jaccard word-overlap similarity score against recent history."""
        if not target or not history:
            return 0.0

        target_words = set(target.lower().split())
        if not target_words:
            return 0.0

        max_sim = 0.0
        for item in history:
            item_words = set(item.lower().split())
            if not item_words:
                continue
            intersection = target_words.intersection(item_words)
            union = target_words.union(item_words)
            sim = len(intersection) / len(union) if union else 0.0
            if sim > max_sim:
                max_sim = sim

        return max_sim
