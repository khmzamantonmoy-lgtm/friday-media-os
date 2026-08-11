"""
strategic_memory.py

Persistent Strategic Memory for ATLAS.
Stores global and per-channel intelligence with OBSERVED / INFERRED / HYPOTHESIS taxonomy.
"""

from typing import Dict, Any, Optional, List
import datetime
import logging
from google.cloud import firestore
from src.atlas.models import EvidenceLevel, LearningInsight

logger = logging.getLogger("strategic_memory")


class StrategicMemory:
    """
    Persistent ATLAS memory. Tracks global platform intelligence and per-channel
    learning signals (winners, failures, experiments, audience profiles).
    Never permanently encodes a conclusion from a single weak data point.
    """

    MINIMUM_DATA_POINTS_FOR_CONCLUSION = 3

    def __init__(self):
        self.db = firestore.Client()

    # ── Global Memory ────────────────────────────────────────────────────────

    def get_global_strategy(self) -> Dict[str, Any]:
        doc = self.db.collection("atlas_strategic_memory").document("global").get()
        return doc.to_dict() if doc.exists else {}

    def update_global_strategy(self, key: str, value: Any, evidence_level: EvidenceLevel) -> None:
        payload = {
            key: {
                "value": value,
                "evidence_level": evidence_level.value,
                "updated_at": datetime.datetime.utcnow().isoformat(),
            }
        }
        self.db.collection("atlas_strategic_memory").document("global").set(payload, merge=True)

    # ── Per-Channel Memory ────────────────────────────────────────────────────

    def get_channel_memory(self, brand_id: str) -> Dict[str, Any]:
        doc = self.db.collection("atlas_strategic_memory").document(f"brand_{brand_id}").get()
        return doc.to_dict() if doc.exists else {}

    def record_winner(self, brand_id: str, content_id: str, insight: LearningInsight) -> None:
        """
        Records a winning content item with its derived mechanism.
        Does NOT conclude 'make more like this' — records the underlying mechanism.
        """
        mem = self.get_channel_memory(brand_id)
        winners = mem.get("winners", [])

        winners.append({
            "content_id": content_id,
            "underlying_mechanism": insight.underlying_mechanism,
            "evidence_level": insight.evidence_level.value,
            "derived_action": insight.derived_action,
            "recorded_at": datetime.datetime.utcnow().isoformat(),
        })

        # Only retain last 30 winners to prevent memory bloat
        winners = winners[-30:]
        self.db.collection("atlas_strategic_memory").document(f"brand_{brand_id}").set(
            {"winners": winners}, merge=True
        )
        logger.info(f"Recorded winner mechanism for {brand_id}: {insight.underlying_mechanism}")

    def record_failure(self, brand_id: str, content_id: str, insight: LearningInsight) -> None:
        """
        Records a failure with its root-cause mechanism (Topic / Execution / Packaging / Audience).
        Only promotes to strategic conclusion when MINIMUM_DATA_POINTS_FOR_CONCLUSION is met.
        """
        mem = self.get_channel_memory(brand_id)
        failures = mem.get("failures", [])

        failures.append({
            "content_id": content_id,
            "failure_type": insight.failure_type.value if insight.failure_type else None,
            "underlying_mechanism": insight.underlying_mechanism,
            "evidence_level": insight.evidence_level.value,
            "derived_action": insight.derived_action,
            "recorded_at": datetime.datetime.utcnow().isoformat(),
        })

        failures = failures[-30:]

        # Elevate to OBSERVED only if the same failure pattern appears 3+ times
        failure_types = [f.get("failure_type") for f in failures if f.get("failure_type")]
        strategic_conclusions = {}
        for ft in set(failure_types):
            count = failure_types.count(ft)
            if count >= self.MINIMUM_DATA_POINTS_FOR_CONCLUSION:
                strategic_conclusions[ft] = {
                    "pattern_count": count,
                    "evidence_level": EvidenceLevel.OBSERVED.value,
                    "note": f"Repeated {ft} pattern detected across {count} content items.",
                }

        self.db.collection("atlas_strategic_memory").document(f"brand_{brand_id}").set(
            {"failures": failures, "strategic_conclusions": strategic_conclusions}, merge=True
        )

    def get_channel_context_for_brief(self, brand_id: str) -> Dict[str, Any]:
        """Returns condensed memory relevant for generating a ContentBrief."""
        mem = self.get_channel_memory(brand_id)
        winners = mem.get("winners", [])
        failures = mem.get("failures", [])
        conclusions = mem.get("strategic_conclusions", {})

        return {
            "recent_winning_mechanisms": [w.get("underlying_mechanism") for w in winners[-5:]],
            "recent_failure_types": [f.get("failure_type") for f in failures[-5:] if f.get("failure_type")],
            "active_strategic_conclusions": conclusions,
        }
