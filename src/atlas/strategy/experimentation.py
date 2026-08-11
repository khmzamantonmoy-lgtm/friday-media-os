"""
experimentation.py

Experimentation Engine for ATLAS.
Tracks single-variable A/B hypothesis experiments per channel.
"""

from typing import Dict, Any, Optional
import uuid
import datetime
from google.cloud import firestore


class ExperimentationEngine:
    """
    Manages controlled experiments on individual content variables (hook, topic, narrative, CTA, pacing, duration).
    """

    def __init__(self):
        self.db = firestore.Client()

    def create_experiment(
        self,
        brand_id: str,
        hypothesis: str,
        variable: str,
        control_value: str,
        test_value: str
    ) -> Dict[str, Any]:
        exp_id = f"exp_{brand_id}_{uuid.uuid4().hex[:6]}"
        data = {
            "experiment_id": exp_id,
            "brand_id": brand_id,
            "hypothesis": hypothesis,
            "variable": variable,
            "control_value": control_value,
            "test_value": test_value,
            "status": "ACTIVE",
            "created_at": datetime.datetime.utcnow().isoformat(),
            "confidence": 0.0,
            "decision": "PENDING"
        }
        self.db.collection("atlas_experiments").document(exp_id).set(data)
        return data

    def record_experiment_result(self, exp_id: str, test_performance: float, control_baseline: float) -> Dict[str, Any]:
        doc_ref = self.db.collection("atlas_experiments").document(exp_id)
        snapshot = doc_ref.get()
        if not snapshot.exists:
            return {"status": "error", "message": f"Experiment {exp_id} not found."}

        delta = test_performance - control_baseline
        decision = "ADOPT_TEST" if delta > 0.15 else ("REJECT_TEST" if delta < -0.10 else "INCONCLUSIVE")
        confidence = min(1.0, abs(delta) * 2.5)

        update_payload = {
            "status": "COMPLETED",
            "test_performance": test_performance,
            "control_baseline": control_baseline,
            "delta": delta,
            "decision": decision,
            "confidence": confidence,
            "completed_at": datetime.datetime.utcnow().isoformat()
        }
        doc_ref.update(update_payload)
        return update_payload
