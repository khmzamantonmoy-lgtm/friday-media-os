"""
tests/tier1_unit/test_focused_regression.py

Focused unit and integration regression tests covering:
1. scheduler lease acquisition & overlapping scheduler prevention
2. stale lease recovery & owner-safe lease release
3. stale youtube_video_id does not incorrectly bypass production (A)
4. valid uploaded youtube_video_id resumes at PUBLIC (B)
5. RENDERED without confirmed upload still uploads normally (C)
6. multiple resumable items are selected deterministically (D)
7. PUBLIC pending verification never becomes COMPLETE (E)
8. processed + public + captions still produces verified-public (F)
9. image generation concurrency is serialized (max_workers=1)
"""

import datetime
import unittest
from unittest.mock import MagicMock, patch, call, ANY
from google.cloud import firestore

from src.engine.brand_worker import BrandWorker
from src.engine.semantic_memory import SemanticMemory
from src.engine.state_machine import ContentState
from src.scheduler.autonomous_scheduler import run_scheduler
from src.workers.image_worker import generate_images


class TestFocusedRegression(unittest.TestCase):

    def setUp(self):
        self.db_patcher = patch("google.cloud.firestore.Client")
        self.mock_db_class = self.db_patcher.start()
        self.mock_db = MagicMock()
        self.mock_db_class.return_value = self.mock_db
        
        # Default mock registry to avoid brand errors
        self.registry_patcher = patch.dict("src.config.brand_registry.BRAND_REGISTRY", {
            "wealthwise": {"daily_target": 4, "voice_id": "default"},
            "kids_universe": {"daily_target": 4, "voice_id": "default"},
            "philosophy": {"daily_target": 4, "voice_id": "default"},
            "bd_threatpulse": {"daily_target": 4, "voice_id": "default"}
        })
        self.registry_patcher.start()

        # Prevent housekeeping from crashing on mock documents in other collections
        self.mock_db.collection.return_value.where.return_value.stream.return_value = []

    def tearDown(self):
        self.db_patcher.stop()
        self.registry_patcher.stop()

    # ---------------------------------------------------------------------------
    # GLOBAL PRODUCTION LEASE TESTS (Invariants 1 & 2)
    # ---------------------------------------------------------------------------

    @patch("src.scheduler.autonomous_scheduler.GoalEngine")
    def test_lease_acquisition_success_and_overlap_prevention(self, mock_goal_engine):
        """A scheduler run acquires a valid lease; a concurrent run is blocked."""
        mock_goal_engine.return_value.count_for_brand.return_value = {
            "verified": 0, "active": 0, "missing": 0, "daily_target": 4
        }

        mock_ref = MagicMock()
        mock_snapshot = MagicMock()
        mock_snapshot.exists = False
        mock_ref.get.return_value = mock_snapshot
        
        self.mock_db.collection.side_effect = lambda coll_name: (
            MagicMock(document=lambda doc_id: mock_ref)
            if coll_name in ["scheduler_leases", "content_items"] else MagicMock()
        )
        
        self.mock_db.transaction.return_value = MagicMock()
        with patch("src.scheduler.autonomous_scheduler.firestore.transactional", lambda f: f):
            result = run_scheduler()
            self.assertEqual(result.get("status"), "success")
            
            mock_snapshot.exists = True
            mock_snapshot.to_dict.return_value = {
                "owner": "other-owner",
                "expires_at": (datetime.datetime.now(datetime.UTC) + datetime.timedelta(minutes=10)).isoformat()
            }
            
            result_overlap = run_scheduler()
            self.assertEqual(result_overlap.get("status"), "lease_denied")

    @patch("src.scheduler.autonomous_scheduler.GoalEngine")
    def test_lease_stale_recovery_and_owner_safety(self, mock_goal_engine):
        """An expired lease is recovered safely."""
        mock_goal_engine.return_value.count_for_brand.return_value = {
            "verified": 0, "active": 0, "missing": 0, "daily_target": 4
        }

        mock_ref = MagicMock()
        mock_snapshot = MagicMock()
        
        mock_snapshot.exists = True
        mock_snapshot.to_dict.return_value = {
            "owner": "old-expired-owner",
            "expires_at": (datetime.datetime.now(datetime.UTC) - datetime.timedelta(minutes=5)).isoformat()
        }
        mock_ref.get.return_value = mock_snapshot
        
        self.mock_db.collection.side_effect = lambda coll_name: (
            MagicMock(document=lambda doc_id: mock_ref)
            if coll_name in ["scheduler_leases", "content_items"] else MagicMock()
        )
        
        with patch("src.scheduler.autonomous_scheduler.firestore.transactional", lambda f: f):
            result = run_scheduler()
            self.assertEqual(result.get("status"), "success")

    # ---------------------------------------------------------------------------
    # RESUMABLE INVARIANTS TESTS (A, B, C, D)
    # ---------------------------------------------------------------------------

    @patch("src.engine.brand_worker.BrandWorker._execute_upload")
    def test_stale_youtube_video_id_does_not_bypass_production(self, mock_upload):
        """Invariant A: A stale youtube_video_id in RENDERED state does NOT bypass upload/generation."""
        worker = BrandWorker()
        mock_upload.return_value = "https://www.youtube.com/watch?v=fresh_upload_id"
        
        mock_doc_ref = MagicMock()
        mock_doc = MagicMock()
        mock_doc.exists = True
        mock_doc.to_dict.return_value = {
            "status": "RENDERED",
            "topic": "Upload check topic",
            "final_video_uri": "gs://bucket/vid.mp4",
            "srt_uri": "gs://bucket/sub.srt",
            "youtube_video_id": "stale_yt_id",  # stale ID present
            "created_at": datetime.datetime.now(datetime.UTC).isoformat()
        }
        mock_doc_ref.get.return_value = mock_doc
        self.mock_db.collection.return_value.document.return_value = mock_doc_ref
        
        worker._process_content("WealthWise_upload_stale", {"id": "wealthwise"}, MagicMock(), "2026-08-09")
        
        # Must execute the upload since current state is RENDERED and not confirmed uploaded (PUBLIC)
        mock_upload.assert_called_once()
        # Must update Firestore with the fresh upload video ID
        mock_doc_ref.update.assert_any_call({"status": "PUBLIC", "youtube_video_id": "fresh_upload_id", "updated_at": ANY})

    @patch("src.engine.brand_worker.BrandWorker._execute_script")
    @patch("src.engine.brand_worker.BrandWorker._execute_upload")
    def test_valid_uploaded_youtube_video_id_resumes_at_public(self, mock_upload, mock_script):
        """Invariant B: A valid uploaded item (RETRY + failed_state=PUBLIC) skips generation and resumes at PUBLIC."""
        worker = BrandWorker()
        
        mock_doc_ref = MagicMock()
        mock_doc = MagicMock()
        mock_doc.exists = True
        mock_doc.to_dict.return_value = {
            "status": "RETRY",
            "topic": "Retry topic",
            "youtube_video_id": "confirmed_upload_id",
            "failed_state": "PUBLIC",  # Confirming previous successful upload
            "created_at": datetime.datetime.now(datetime.UTC).isoformat()
        }
        mock_doc_ref.get.return_value = mock_doc
        self.mock_db.collection.return_value.document.return_value = mock_doc_ref
        
        worker._process_content("WealthWise_upload_confirmed", {"id": "wealthwise"}, MagicMock(), "2026-08-09")
        
        # Generation/Upload must NOT be run
        mock_script.assert_not_called()
        mock_upload.assert_not_called()
        # Status must jump directly to PUBLIC and worker returns early
        mock_doc_ref.update.assert_any_call({"status": "PUBLIC", "updated_at": ANY})

    @patch("src.engine.brand_worker.BrandWorker._execute_upload")
    def test_rendered_without_confirmed_upload_still_uploads_normally(self, mock_upload):
        """Invariant C: RENDERED without confirmed upload still uploads normally."""
        worker = BrandWorker()
        mock_upload.return_value = "https://www.youtube.com/watch?v=normal_upload_id"
        
        mock_doc_ref = MagicMock()
        mock_doc = MagicMock()
        mock_doc.exists = True
        mock_doc.to_dict.return_value = {
            "status": "RENDERED",
            "topic": "Upload normal topic",
            "final_video_uri": "gs://bucket/vid.mp4",
            "srt_uri": "gs://bucket/sub.srt",
            "created_at": datetime.datetime.now(datetime.UTC).isoformat()
        }
        mock_doc_ref.get.return_value = mock_doc
        self.mock_db.collection.return_value.document.return_value = mock_doc_ref
        
        worker._process_content("WealthWise_normal_upload", {"id": "wealthwise"}, MagicMock(), "2026-08-09")
        
        mock_upload.assert_called_once()
        mock_doc_ref.update.assert_any_call({"status": "PUBLIC", "youtube_video_id": "normal_upload_id", "updated_at": ANY})

    def test_multiple_resumable_items_are_selected_deterministically(self):
        """Invariant D: Selects from multiple active items based on deterministic priority score."""
        worker = BrandWorker()
        today_date = datetime.datetime.now(datetime.UTC).date()
        today_iso = datetime.datetime.now(datetime.UTC).isoformat()
        
        # Candidates: item1 (ASSETS_READY, priority 5), item2 (UPLOADING, priority 2)
        mock_doc1 = MagicMock()
        mock_doc1.id = "WW_assets_ready"
        mock_doc1.to_dict.return_value = {
            "brand_id": "wealthwise",
            "status": "ASSETS_READY",
            "created_at": today_iso
        }
        
        mock_doc2 = MagicMock()
        mock_doc2.id = "WW_uploading"
        mock_doc2.to_dict.return_value = {
            "brand_id": "wealthwise",
            "status": "UPLOADING",
            "created_at": today_iso
        }
        
        self.mock_db.collection.return_value.where.return_value.stream.return_value = [mock_doc1, mock_doc2]
        
        selected_id, selected_data = worker._find_resumable_item("wealthwise", today_date)
        
        # Must select UPLOADING (priority 2) over ASSETS_READY (priority 5)
        self.assertEqual(selected_id, "WW_uploading")

    # ---------------------------------------------------------------------------
    # VERIFICATION HOUSEKEEPING TESTS (E, F)
    # ---------------------------------------------------------------------------

    @patch("src.engine.brand_worker.BrandWorker._execute_upload")
    @patch("src.engine.brand_worker.PublicationVerifier")
    def test_public_pending_verification_never_becomes_complete(self, mock_verifier_class, mock_upload):
        """Invariant E: A pending verification does not transition to COMPLETE and remains in PUBLIC."""
        worker = BrandWorker()
        mock_verifier = MagicMock()
        mock_verifier_class.return_value = mock_verifier
        mock_verifier.verify_status.return_value = "PENDING"
        worker.verifier = mock_verifier
        
        mock_doc_ref = MagicMock()
        mock_doc = MagicMock()
        mock_doc.exists = True
        mock_doc.to_dict.return_value = {
            "status": "PUBLIC",
            "topic": "Pending topic",
            "youtube_video_id": "pending_yt_id",
            "youtube_verified": False,
            "created_at": datetime.datetime.now(datetime.UTC).isoformat()
        }
        mock_doc_ref.get.return_value = mock_doc
        self.mock_db.collection.return_value.document.return_value = mock_doc_ref
        
        mock_memory = MagicMock()
        worker._process_content("WealthWise_verification_pending", {"id": "wealthwise"}, mock_memory, "2026-08-09")
        
        # Must execute verify_status
        mock_verifier.verify_status.assert_called_once_with("WealthWise_verification_pending", "pending_yt_id", "wealthwise")
        # Status should NOT update to COMPLETE (no COMPLETE update calls)
        for call_args in mock_doc_ref.update.call_args_list:
            status_arg = call_args[0][0].get("status")
            self.assertNotEqual(status_arg, "COMPLETE")

    @patch("src.engine.brand_worker.BrandWorker._execute_upload")
    @patch("src.engine.brand_worker.PublicationVerifier")
    def test_processed_public_captions_still_produces_verified_public(self, mock_verifier_class, mock_upload):
        """Invariant F: A processed and verified video is successfully completed."""
        worker = BrandWorker()
        mock_verifier = MagicMock()
        mock_verifier_class.return_value = mock_verifier
        mock_verifier.verify_status.return_value = "VERIFIED"
        worker.verifier = mock_verifier
        
        mock_doc_ref = MagicMock()
        mock_doc = MagicMock()
        mock_doc.exists = True
        mock_doc.to_dict.return_value = {
            "status": "PUBLIC",
            "topic": "Completed topic",
            "youtube_video_id": "completed_yt_id",
            "youtube_verified": False,
            "created_at": datetime.datetime.now(datetime.UTC).isoformat()
        }
        mock_doc_ref.get.return_value = mock_doc
        self.mock_db.collection.return_value.document.return_value = mock_doc_ref
        
        mock_memory = MagicMock()
        worker._process_content("WealthWise_verification_happy", {"id": "wealthwise"}, mock_memory, "2026-08-09")
        
        # Must execute verify_status and update memory
        mock_verifier.verify_status.assert_called_once_with("WealthWise_verification_happy", "completed_yt_id", "wealthwise")
        mock_memory.add_memory.assert_called_once_with("WealthWise_verification_happy", "Completed topic")
        
        # Must transition sequentially to COMPLETE
        mock_doc_ref.update.assert_any_call({"status": "CAPTIONS_VERIFIED", "updated_at": ANY})
        mock_doc_ref.update.assert_any_call({"status": "MEMORY_UPDATED", "updated_at": ANY})
        mock_doc_ref.update.assert_any_call({"status": "COMPLETE", "updated_at": ANY})

    # ---------------------------------------------------------------------------
    # IMAGE SERIALIZATION CONCURRENCY TESTS
    # ---------------------------------------------------------------------------

    def test_image_generation_concurrency_is_one(self):
        """generate_images sets max_workers to exactly 1 (serialized concurrency)."""
        with patch("src.workers.image_worker.ThreadPoolExecutor") as mock_executor:
            generate_images([{"text": "Scene 1", "timestamp": 0}], {"id": "wealthwise"}, "wealthwise_concurrency")
            mock_executor.assert_called_once_with(max_workers=1)


if __name__ == "__main__":
    unittest.main()
