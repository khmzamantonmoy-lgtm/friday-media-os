import logging
import datetime
from google.cloud import firestore
from src.engine.brand_worker import BrandWorker
from src.config.brand_registry import BRAND_REGISTRY

logger = logging.getLogger(__name__)

class GoalEngine:
    def __init__(self):
        self.db = firestore.Client()
        self.worker = BrandWorker()

    @staticmethod
    def normalize_to_date(created_at) -> datetime.date | None:
        """
        Robustly normalizes created_at values to a datetime.date in UTC.
        Handles:
          - ISO string (naive or timezone-aware)
          - Firestore Timestamps or datetime objects (naive or timezone-aware)
          - Missing created_at (None/empty)
          - Malformed created_at
        """
        if not created_at:
            return None

        # 1. Handle timezone-aware or naive datetimes and Timestamp objects
        if hasattr(created_at, "date"):
            try:
                # If timezone aware, convert to UTC first
                if getattr(created_at, "tzinfo", None) is not None:
                    return created_at.astimezone(datetime.UTC).date()
                return created_at.date()
            except Exception:
                pass

        # 2. Handle string formats (e.g. ISO string representation)
        if isinstance(created_at, str):
            try:
                # Replace trailing 'Z' with +00:00 for robust parsing on older python versions
                normalized_str = created_at.replace("Z", "+00:00")
                dt = datetime.datetime.fromisoformat(normalized_str)
                if dt.tzinfo is not None:
                    return dt.astimezone(datetime.UTC).date()
                return dt.date()
            except Exception:
                # Fallback: attempt simple split "YYYY-MM-DD" parsing
                try:
                    parts = created_at.split("T")[0].split("-")
                    if len(parts) == 3 and len(parts[0]) == 4:
                        return datetime.date(int(parts[0]), int(parts[1]), int(parts[2]))
                except Exception:
                    pass

        return None

    def count_for_brand(self, brand_id: str) -> dict:
        """
        Query content_items (the authoritative production-state collection)
        and return the verified, active, and missing counts for today.

        Production contract:
          VERIFIED: status == COMPLETE AND youtube_video_id exists AND youtube_verified == True
          ACTIVE:   status in ACTIVE_STATUSES (includes PUBLIC pending verification)
          FAILED and COMPLETE-unverified: NOT counted as active or verified

        'available' = verified + active
        missing     = max(0, daily_target - available)

        Note: PUBLIC + youtube_video_id + youtube_verified != True counts as ACTIVE,
        not VERIFIED. It has been uploaded but not yet confirmed processed/public.
        It still occupies a production slot and must not cause a duplicate cycle.
        """
        brand_cfg = BRAND_REGISTRY.get(brand_id)
        if not brand_cfg:
            logger.error(f"Brand {brand_id} not found in BRAND_REGISTRY.")
            return {"verified": 0, "active": 0, "missing": 0, "daily_target": 0}

        daily_target = brand_cfg.get("daily_target", 1)

        # Get today's date in UTC timezone
        today_date = datetime.datetime.now(datetime.UTC).date()

        # Query content_items for this brand — no date filter in Firestore
        # (date filtering is applied in Python below using normalize_to_date).
        docs = list(
            self.db.collection("content_items")
            .where("brand_id", "==", brand_id)
            .stream()
        )

        # Statuses that represent in-flight work occupying a production slot.
        # FAILED and COMPLETE-unverified must NOT count.
        ACTIVE_STATUSES = {
            "NEW", "TOPIC_SELECTED", "SCRIPT_READY", "ASSETS_READY",
            "RENDERING", "RENDERED", "UPLOADING", "PUBLIC",
            "CAPTIONS_VERIFIED", "MEMORY_UPDATED", "RETRY",
        }

        verified = 0
        active = 0

        for doc in docs:
            data = doc.to_dict()

            # Date filter: only count items belonging to the current UTC production day
            created_date = self.normalize_to_date(data.get("created_at"))
            if created_date != today_date:
                continue

            status = data.get("status")

            if status == "COMPLETE":
                # Only counts toward verified if fully confirmed by PublicationVerifier
                if data.get("youtube_video_id") and data.get("youtube_verified") is True:
                    verified += 1
                # COMPLETE but unverified: does not count as active or verified

            elif status in ACTIVE_STATUSES:
                # PUBLIC with a yt_id but youtube_verified != True is ACTIVE (pending verification)
                # This prevents launching a duplicate cycle for already-uploaded content
                active += 1

        available = verified + active
        missing = max(0, daily_target - available)
        return {
            "verified": verified,
            "active": active,
            "available": available,
            "missing": missing,
            "daily_target": daily_target,
        }

    def evaluate(self, brand_id: str):
        """
        Evaluate goals for a brand and trigger generation cycles if missing > 0.
        Reads content_items as the authoritative production-state collection.
        GoalEngine.evaluate() is preserved for backward compatibility but the
        scheduler invokes worker.run_cycle() directly for round-robin control.
        """
        logger.info(f"Evaluating goals for {brand_id}")

        counts = self.count_for_brand(brand_id)
        if counts["daily_target"] == 0:
            return

        logger.info(
            f"Brand {brand_id}: target={counts['daily_target']}, "
            f"verified={counts['verified']}, active={counts['active']}, "
            f"missing={counts['missing']}"
        )

        if counts["missing"] > 0:
            for i in range(counts["missing"]):
                logger.info(f"Launching cycle {i + 1}/{counts['missing']} for {brand_id}")
                try:
                    self.worker.run_cycle(brand_id)
                except Exception as e:
                    logger.error(f"Error in brand worker cycle: {e}")
