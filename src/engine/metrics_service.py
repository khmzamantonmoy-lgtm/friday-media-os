import datetime
import logging
from google.cloud import firestore

logger = logging.getLogger(__name__)

class MetricsService:
    def __init__(self):
        self.db = firestore.Client()

    def update_metrics(self, brand_id: str, date: str, metrics: dict):
        """
        Write per-brand metrics to Firestore collection: production_metrics/{brand_id}/daily/{date}
        """
        try:
            doc_ref = self.db.collection("production_metrics").document(brand_id).collection("daily").document(date)
            doc_ref.set(metrics, merge=True)
            logger.info(f"Updated metrics for {brand_id} on {date}")
        except Exception as e:
            logger.error(f"Failed to update metrics: {e}")

    def increment_metric(self, brand_id: str, date: str, field: str, value: int = 1):
        try:
            doc_ref = self.db.collection("production_metrics").document(brand_id).collection("daily").document(date)
            doc_ref.set({
                field: firestore.Increment(value)
            }, merge=True)
        except Exception as e:
            logger.error(f"Failed to increment metric: {e}")
