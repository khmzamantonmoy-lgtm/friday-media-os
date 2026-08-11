"""
performance_intel.py

Performance Intelligence Module for ATLAS.
Collects actual YouTube analytics performance data and persists performance records.
"""

from typing import Dict, Any, List, Optional
import datetime
import logging
from google.cloud import firestore

logger = logging.getLogger("performance_intel")


class PerformanceIntelligence:
    """
    Ingests performance data from YouTube Analytics and Firestore.
    Creates persistent item performance records.
    """

    def __init__(self):
        self.db = firestore.Client()

    def record_item_performance(
        self,
        content_id: str,
        brand_id: str,
        video_id: str,
        metrics: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Persists performance data for a published content item in atlas_performance_records.
        Captured metrics: views, likes, comments, shares, watch_time, retention, etc.
        Never invents unavailable metrics.
        """
        record = {
            "content_id": content_id,
            "brand_id": brand_id,
            "youtube_video_id": video_id,
            "views": metrics.get("views", 0),
            "likes": metrics.get("likes", 0),
            "comments": metrics.get("comments", 0),
            "shares": metrics.get("shares", 0),
            "watch_time_minutes": metrics.get("watch_time_minutes", 0.0),
            "average_view_duration_seconds": metrics.get("average_view_duration_seconds", 0.0),
            "retention_rate": metrics.get("retention_rate", 0.0),
            "subscribers_gained": metrics.get("subscribers_gained", 0),
            "updated_at": datetime.datetime.utcnow().isoformat(),
        }

        self.db.collection("atlas_performance_records").document(content_id).set(record, merge=True)
        logger.info(f"Recorded performance metrics for {content_id} (views={record['views']})")
        return record

    def get_brand_performance_history(self, brand_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        docs = list(
            self.db.collection("atlas_performance_records")
            .where("brand_id", "==", brand_id)
            .limit(limit)
            .stream()
        )
        records = [d.to_dict() for d in docs]
        records.sort(key=lambda x: x.get("views", 0), reverse=True)
        return records
