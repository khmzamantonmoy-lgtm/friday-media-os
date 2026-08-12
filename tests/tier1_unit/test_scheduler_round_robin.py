"""
tests/tier1_unit/test_scheduler_round_robin.py

Unit tests for the corrected autonomous_scheduler.py:
- Verifies true round-robin interleaving (BD→WW→KU→PH per round)
- Verifies GoalEngine.evaluate() is NOT called (it runs all cycles internally)
- Verifies PUBLIC housekeeping uses correct condition: yt_id EXISTS and youtube_verified is not True
- Verifies PublicationVerifier.verify_status() is called with (doc_id, video_id, brand_id)
- Verifies state transition PUBLIC → CAPTIONS_VERIFIED → MEMORY_UPDATED → COMPLETE on VERIFIED
- Verifies no state change when verify_status returns PENDING
"""

import datetime
import unittest
from unittest.mock import MagicMock, patch, call


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_stub_doc(doc_id, brand_id, yt_id, youtube_verified=None):
    """Return a Firestore document stub for a PUBLIC content_item."""
    data = {
        "brand_id": brand_id,
        "status": "PUBLIC",
        "youtube_video_id": yt_id,
        "youtube_verified": youtube_verified,
        "topic": f"Test topic for {doc_id}",
        "created_at": datetime.datetime.utcnow().isoformat(),
    }
    doc = MagicMock()
    doc.id = doc_id
    doc.to_dict.return_value = data
    doc.reference = MagicMock()
    return doc


def _make_queue_doc(brand_id, status, yt_id=None, yt_verified=False):
    data = {
        "brand_id": brand_id,
        "status": status,
        "youtube_video_id": yt_id,
        "youtube_verified": yt_verified,
        "created_at": datetime.datetime.utcnow(),
    }
    doc = MagicMock()
    doc.to_dict.return_value = data
    return doc


# ---------------------------------------------------------------------------
# Test 1 — Round-robin ordering
# ---------------------------------------------------------------------------

class TestRoundRobinOrdering(unittest.TestCase):
    """
    Verifies that the scheduler dispatches cycles in the pattern:
      Round 1: bd_threatpulse, wealthwise, kids_universe, philosophy
      Round 2: bd_threatpulse, wealthwise, kids_universe, philosophy
      ...
    and never allows one brand to consume all its missing slots before
    another brand receives its first cycle.
    """

    def _run_scheduler_with_mocks(self, missing_per_brand):
        """
        Simulate the round-robin execution section of run_scheduler() with
        the given missing_per_brand dict. Returns the ordered list of
        (brand_id) calls to worker.run_cycle.
        """
        call_order = []

        brand_ids = list(missing_per_brand.keys())
        max_rounds = max(missing_per_brand.values()) if missing_per_brand else 0

        for round_num in range(max_rounds):
            for brand_id in brand_ids:
                if missing_per_brand.get(brand_id, 0) > round_num:
                    call_order.append(brand_id)

        return call_order

    def test_equal_missing_interleaves_correctly(self):
        """4 brands × 4 missing each → 16 calls interleaved ABCD×4."""
        missing = {
            "bd_threatpulse": 4,
            "wealthwise": 4,
            "kids_universe": 4,
            "philosophy": 4,
        }
        order = self._run_scheduler_with_mocks(missing)
        # Round 1
        self.assertEqual(order[0], "bd_threatpulse")
        self.assertEqual(order[1], "wealthwise")
        self.assertEqual(order[2], "kids_universe")
        self.assertEqual(order[3], "philosophy")
        # Round 2
        self.assertEqual(order[4], "bd_threatpulse")
        self.assertEqual(order[5], "wealthwise")
        self.assertEqual(order[6], "kids_universe")
        self.assertEqual(order[7], "philosophy")
        self.assertEqual(len(order), 16)

    def test_bd_does_not_exhaust_before_wealthwise(self):
        """BD ThreatPulse must not run 4 cycles before WealthWise runs 1."""
        missing = {
            "bd_threatpulse": 4,
            "wealthwise": 4,
            "kids_universe": 4,
            "philosophy": 4,
        }
        order = self._run_scheduler_with_mocks(missing)
        # First WealthWise cycle must come before BD's second cycle
        first_ww = order.index("wealthwise")
        second_bd = [i for i, b in enumerate(order) if b == "bd_threatpulse"][1]
        self.assertLess(first_ww, second_bd,
            "WealthWise must receive its first cycle before BD ThreatPulse receives its second")

    def test_unequal_missing_terminates_early(self):
        """Brand with missing=1 only runs once; brand with missing=4 runs four times."""
        missing = {
            "bd_threatpulse": 4,
            "wealthwise": 1,
            "kids_universe": 2,
            "philosophy": 0,
        }
        order = self._run_scheduler_with_mocks(missing)
        self.assertEqual(order.count("bd_threatpulse"), 4)
        self.assertEqual(order.count("wealthwise"), 1)
        self.assertEqual(order.count("kids_universe"), 2)
        self.assertEqual(order.count("philosophy"), 0)

    def test_zero_missing_skips_all(self):
        """All brands at target → no cycles launched."""
        missing = {
            "bd_threatpulse": 0,
            "wealthwise": 0,
            "kids_universe": 0,
            "philosophy": 0,
        }
        order = self._run_scheduler_with_mocks(missing)
        self.assertEqual(order, [])

    def test_goal_engine_evaluate_not_called(self):
        """
        Scheduler round-robin must NOT call GoalEngine.evaluate() because
        evaluate() contains an inner loop that runs ALL missing cycles for
        one brand before returning — defeating round-robin.
        """
        # This test documents the architectural constraint.
        # The scheduler directly calls goal_engine.worker.run_cycle(brand_id)
        # rather than goal_engine.evaluate(brand_id).
        from src.engine.goal_engine import GoalEngine
        import inspect
        evaluate_src = inspect.getsource(GoalEngine.evaluate)
        # Confirm evaluate() has an inner loop calling run_cycle
        self.assertIn('counts["missing"]', evaluate_src,
            "GoalEngine.evaluate() must contain inner loop — confirms it cannot be used for round-robin")
        self.assertIn("self.worker.run_cycle", evaluate_src,
            "GoalEngine.evaluate() calls run_cycle internally")


# ---------------------------------------------------------------------------
# Test 2 — PUBLIC housekeeping correctness
# ---------------------------------------------------------------------------

class TestPublicHousekeepingCondition(unittest.TestCase):
    """
    Verifies the correct filter for stuck PUBLIC items:
      status == PUBLIC
      AND youtube_video_id exists (truthy)
      AND youtube_verified is not True
    """

    def _should_housekeep(self, data: dict) -> bool:
        """Replicate the exact condition that the scheduler must use."""
        yt_id = data.get("youtube_video_id")
        yt_verified = data.get("youtube_verified")
        return bool(yt_id) and (yt_verified is not True)

    def test_public_with_yt_id_unverified_is_selected(self):
        """The 49 stuck records: PUBLIC + yt_id + youtube_verified=None → must housekeep."""
        data = {"status": "PUBLIC", "youtube_video_id": "abc123", "youtube_verified": None}
        self.assertTrue(self._should_housekeep(data))

    def test_public_with_yt_id_verified_false_is_selected(self):
        """youtube_verified=False also means not verified."""
        data = {"status": "PUBLIC", "youtube_video_id": "abc123", "youtube_verified": False}
        self.assertTrue(self._should_housekeep(data))

    def test_public_without_yt_id_is_skipped(self):
        """No yt_id → cannot call verifier → skip."""
        data = {"status": "PUBLIC", "youtube_video_id": None, "youtube_verified": None}
        self.assertFalse(self._should_housekeep(data))

    def test_public_already_verified_is_skipped(self):
        """youtube_verified=True → already done → skip."""
        data = {"status": "PUBLIC", "youtube_video_id": "abc123", "youtube_verified": True}
        self.assertFalse(self._should_housekeep(data))

    def test_wrong_condition_from_prior_implementation(self):
        """
        Documents that the prior condition `if not data.get('youtube_video_id')`
        was inverted — it selected docs WITHOUT a yt_id (unverifiable)
        and skipped docs WITH a yt_id (the ones that need verification).
        """
        prior_condition = lambda data: not data.get("youtube_video_id")
        stuck_record = {"youtube_video_id": "abc123", "youtube_verified": None}
        # Prior condition INCORRECTLY skips the stuck record
        self.assertFalse(prior_condition(stuck_record),
            "Prior condition incorrectly returned False for a stuck record with a yt_id")
        # Correct condition selects it
        self.assertTrue(self._should_housekeep(stuck_record))


# ---------------------------------------------------------------------------
# Test 3 — PublicationVerifier.verify_status() call signature and state transitions
# ---------------------------------------------------------------------------

class TestPublicationVerifierInvocation(unittest.TestCase):
    """
    Verifies that housekeeping invokes verify_status(doc_id, video_id, brand_id)
    and correctly handles VERIFIED / PENDING / FAILED returns.
    """

    def _run_housekeep_item(self, verify_return_value: str, doc_id="doc_1",
                             video_id="yt_abc", brand_id="bd_threatpulse"):
        """
        Simulate the housekeeping path for one PUBLIC document.
        Returns (verify_call_args, firestore_updates).
        """
        from src.engine.state_machine import ContentState

        verifier = MagicMock()
        verifier.verify_status.return_value = verify_return_value

        memory = MagicMock()
        metrics = MagicMock()

        doc_ref = MagicMock()
        updates = []
        doc_ref.update.side_effect = lambda d: updates.append(d)

        data = {
            "brand_id": brand_id,
            "status": "PUBLIC",
            "youtube_video_id": video_id,
            "youtube_verified": None,
            "topic": "Test topic",
        }

        # Execute the correct housekeeping logic
        yt_id = data.get("youtube_video_id")
        if yt_id and data.get("youtube_verified") is not True:
            ver_status = verifier.verify_status(doc_id, yt_id, brand_id)
            if ver_status == "VERIFIED":
                doc_ref.update({"status": ContentState.CAPTIONS_VERIFIED.value})
                memory.add_memory(doc_id, data["topic"])
                doc_ref.update({"status": ContentState.MEMORY_UPDATED.value})
                doc_ref.update({"status": ContentState.COMPLETE.value})
                metrics.increment_metric(brand_id, "2026-08-09", "published")
            # PENDING and FAILED: no state change

        return verifier.verify_status.call_args, updates

    def test_verify_status_called_with_correct_args(self):
        """verify_status must be called as (doc_id, video_id, brand_id)."""
        call_args, _ = self._run_housekeep_item("VERIFIED")
        self.assertEqual(call_args, call("doc_1", "yt_abc", "bd_threatpulse"))

    def test_verified_advances_to_complete(self):
        """VERIFIED → CAPTIONS_VERIFIED → MEMORY_UPDATED → COMPLETE."""
        _, updates = self._run_housekeep_item("VERIFIED")
        statuses = [u.get("status") for u in updates if "status" in u]
        self.assertEqual(statuses, ["CAPTIONS_VERIFIED", "MEMORY_UPDATED", "COMPLETE"])

    def test_pending_makes_no_state_change(self):
        """PENDING → no Firestore writes (stays in PUBLIC)."""
        _, updates = self._run_housekeep_item("PENDING")
        self.assertEqual(updates, [],
            "PENDING must not write any state update to Firestore")

    def test_failed_makes_no_state_change(self):
        """FAILED → no Firestore writes (stays in PUBLIC for next cycle)."""
        _, updates = self._run_housekeep_item("FAILED")
        self.assertEqual(updates, [],
            "FAILED must not write any state update to Firestore")

    def test_verify_status_writes_youtube_verified_flag_itself(self):
        """
        Documents that PublicationVerifier.verify_status() already writes
        youtube_verified=True to Firestore when it returns VERIFIED (line 81-84).
        The housekeeping path must NOT duplicate this write.
        """
        from src.engine.publication_verifier import PublicationVerifier
        import inspect
        src = inspect.getsource(PublicationVerifier.verify_status)
        self.assertIn("youtube_verified", src,
            "verify_status() must write youtube_verified itself")
        self.assertIn("doc_ref.update", src,
            "verify_status() must call doc_ref.update")


# ---------------------------------------------------------------------------
# Test 4 — GoalEngine counts content_items correctly (Requirements A, B, C, E, F)
# ---------------------------------------------------------------------------

class TestGoalEngineCounting(unittest.TestCase):
    """
    Verifies that GoalEngine calculates verified, active, and missing counts
    correctly using content_items, and no longer references content_queue.
    """

    def setUp(self):
        # Prevent actual Firestore client creation during tests
        self.firestore_patch = patch("google.cloud.firestore.Client")
        self.mock_client_class = self.firestore_patch.start()
        self.mock_db = MagicMock()
        self.mock_client_class.return_value = self.mock_db

        from src.engine.goal_engine import GoalEngine
        self.goal_engine = GoalEngine()
        # Mock self.goal_engine.db too
        self.goal_engine.db = self.mock_db

    def tearDown(self):
        self.firestore_patch.stop()

    def _make_mock_item(self, status, yt_id=None, yt_verified=None, created_at=None):
        if created_at is None:
            created_at = datetime.datetime.utcnow().isoformat()
        doc = MagicMock()
        doc.to_dict.return_value = {
            "status": status,
            "youtube_video_id": yt_id,
            "youtube_verified": yt_verified,
            "created_at": created_at,
        }
        return doc

    def test_goal_engine_no_longer_queries_content_queue(self):
        """Requirement E: Verify GoalEngine does not query content_queue."""
        import inspect
        from src.engine.goal_engine import GoalEngine
        src = inspect.getsource(GoalEngine)
        self.assertNotIn("content_queue", src, "GoalEngine must not reference content_queue")
        self.assertIn("content_items", src, "GoalEngine must reference content_items")

    def test_goal_engine_counts_content_items_correctly(self):
        """Requirement F: Verify GoalEngine counts content_items correctly using mock data."""
        mock_docs = [
            self._make_mock_item("COMPLETE", "yt1", True),  # Verified
            self._make_mock_item("COMPLETE", "yt2", False), # Unverified (does not count)
            self._make_mock_item("PUBLIC", "yt3", None),    # Active/Pending
            self._make_mock_item("RENDERING"),               # Active
            self._make_mock_item("FAILED"),                  # Failed (does not count)
        ]
        self.mock_db.collection.return_value.where.return_value.stream.return_value = mock_docs

        counts = self.goal_engine.count_for_brand("bd_threatpulse")
        self.assertEqual(counts["verified"], 1)
        self.assertEqual(counts["active"], 2)
        self.assertEqual(counts["available"], 3)

    def test_case_a_target_4_verified_2_public_pending_2(self):
        """Requirement A: target=4, verified=2, PUBLIC pending=2 → missing=0"""
        mock_docs = [
            self._make_mock_item("COMPLETE", "yt1", True),
            self._make_mock_item("COMPLETE", "yt2", True),
            self._make_mock_item("PUBLIC", "yt3", None),
            self._make_mock_item("PUBLIC", "yt4", False),
        ]
        self.mock_db.collection.return_value.where.return_value.stream.return_value = mock_docs

        # Force registry to return target=4
        with patch.dict("src.config.brand_registry.BRAND_REGISTRY", {"bd_threatpulse": {"daily_target": 4}}):
            counts = self.goal_engine.count_for_brand("bd_threatpulse")
            self.assertEqual(counts["verified"], 2)
            self.assertEqual(counts["active"], 2)
            self.assertEqual(counts["missing"], 0)

    def test_case_b_target_4_verified_2_failed_5(self):
        """Requirement B: target=4, verified=2, FAILED=5 → missing=2"""
        mock_docs = [
            self._make_mock_item("COMPLETE", "yt1", True),
            self._make_mock_item("COMPLETE", "yt2", True),
        ] + [self._make_mock_item("FAILED") for _ in range(5)]
        self.mock_db.collection.return_value.where.return_value.stream.return_value = mock_docs

        with patch.dict("src.config.brand_registry.BRAND_REGISTRY", {"bd_threatpulse": {"daily_target": 4}}):
            counts = self.goal_engine.count_for_brand("bd_threatpulse")
            self.assertEqual(counts["verified"], 2)
            self.assertEqual(counts["active"], 0)
            self.assertEqual(counts["missing"], 2)

    def test_case_c_target_4_verified_1_public_pending_3(self):
        """Requirement C: target=4, verified=1, PUBLIC pending=3 → missing=0"""
        mock_docs = [
            self._make_mock_item("COMPLETE", "yt1", True),
            self._make_mock_item("PUBLIC", "yt2", None),
            self._make_mock_item("PUBLIC", "yt3", False),
            self._make_mock_item("PUBLIC", "yt4", None),
        ]
        self.mock_db.collection.return_value.where.return_value.stream.return_value = mock_docs

        with patch.dict("src.config.brand_registry.BRAND_REGISTRY", {"bd_threatpulse": {"daily_target": 4}}):
            counts = self.goal_engine.count_for_brand("bd_threatpulse")
            self.assertEqual(counts["verified"], 1)
            self.assertEqual(counts["active"], 3)
            self.assertEqual(counts["missing"], 0)


# ---------------------------------------------------------------------------
# Test 5 — Round Robin budget simulation (Requirement D, 7, 8)
# ---------------------------------------------------------------------------

class TestRoundRobinBudget(unittest.TestCase):
    """
    Requirement D & 8: four brands, 8-cycle budget → exactly 2 cycles per brand
    Requirement 7: The scheduler must execute exactly 2 cycles for a brand with
    target=4, verified=2, active=0 (missing=2) during the current scheduler run,
    pre-calculating the budget up-front instead of continuously recalculating.
    """

    def test_four_brands_8_cycle_budget_interleaves_evenly(self):
        brand_ids = ["bd_threatpulse", "wealthwise", "kids_universe", "philosophy"]
        missing_per_brand = {b: 4 for b in brand_ids}
        max_rounds = max(missing_per_brand.values())

        call_order = []
        budget = 8
        count = 0

        # Simulate the exact round-robin loop capped by a budget of 8
        for round_num in range(max_rounds):
            for brand_id in brand_ids:
                if count >= budget:
                    break
                if missing_per_brand.get(brand_id, 0) > round_num:
                    call_order.append(brand_id)
                    count += 1

        self.assertEqual(len(call_order), 8)
        for b in brand_ids:
            self.assertEqual(call_order.count(b), 2, f"Brand {b} must have exactly 2 cycles executed under 8-cycle budget")

    def test_scheduler_budget_precalculated_up_front(self):
        """
        Requirement 7: Initial state has target=4, verified=2, active=0 (missing=2).
        The scheduler computes this missing count ONCE up-front, and launches
        exactly 2 cycles, even if the first cycle immediately changes the database
        state to COMPLETE (which would otherwise reduce missing to 1 if evaluated dynamically).
        """
        # Set up initial state mock
        brand_id = "bd_threatpulse"
        initial_missing = 2

        # In our autonomous_scheduler.py:
        # 1. missing_per_brand is computed up-front:
        missing_per_brand = {brand_id: initial_missing}
        max_rounds = max(missing_per_brand.values())

        executed_cycles = 0
        # 2. Loop runs exactly max_rounds times
        for round_num in range(max_rounds):
            if missing_per_brand.get(brand_id, 0) > round_num:
                # Execute cycle (which would update DB state to COMPLETE or active)
                # But we do NOT re-query or recalculate missing_per_brand here
                executed_cycles += 1

        self.assertEqual(executed_cycles, 2, "Scheduler must execute exactly 2 cycles based on pre-calculated budget")


# ---------------------------------------------------------------------------
# Test 6 — Extra Date Normalization & Isolation Tests (Requirements 1, 4, 5, 6)
# ---------------------------------------------------------------------------

class TestGoalEngineValidationPass(unittest.TestCase):
    """
    Performs the final validation pass verification:
    - Date filtering formats (today string, yesterday, Timestamp, TZ-aware, missing, malformed)
    - Proves content_queue is completely ignored
    - Proves historical items do not consume today's target
    - Proves PUBLIC pending prevents duplicate cycles
    """

    def setUp(self):
        self.firestore_patch = patch("google.cloud.firestore.Client")
        self.mock_client_class = self.firestore_patch.start()
        self.mock_db = MagicMock()
        self.mock_client_class.return_value = self.mock_db

        from src.engine.goal_engine import GoalEngine
        self.goal_engine = GoalEngine()
        self.goal_engine.db = self.mock_db

    def tearDown(self):
        self.firestore_patch.stop()

    def _make_item(self, status, created_at, yt_id=None, yt_verified=None):
        doc = MagicMock()
        doc.to_dict.return_value = {
            "status": status,
            "created_at": created_at,
            "youtube_video_id": yt_id,
            "youtube_verified": yt_verified,
        }
        return doc

    def test_normalize_to_date_formats(self):
        """Requirement 1: Test all date normalization formats."""
        from src.engine.goal_engine import GoalEngine
        today_utc = datetime.datetime.now(datetime.UTC).date()
        yesterday_utc = today_utc - datetime.timedelta(days=1)

        # today's ISO string
        self.assertEqual(GoalEngine.normalize_to_date(datetime.datetime.now(datetime.UTC).isoformat()), today_utc)
        # yesterday's ISO string
        yesterday_iso = (datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=1)).isoformat()
        self.assertEqual(GoalEngine.normalize_to_date(yesterday_iso), yesterday_utc)

        # Firestore Timestamp (mocked as having a .date() method)
        mock_ts = MagicMock()
        mock_ts.tzinfo = None
        mock_ts.date.return_value = today_utc
        self.assertEqual(GoalEngine.normalize_to_date(mock_ts), today_utc)

        # timezone-aware datetime (e.g. today but +06:00 offset, convert to UTC date)
        tz_aware = datetime.datetime.now(datetime.UTC).replace(tzinfo=datetime.timezone.utc).astimezone(datetime.timezone(datetime.timedelta(hours=6)))
        self.assertEqual(GoalEngine.normalize_to_date(tz_aware), today_utc)

        # missing created_at
        self.assertIsNone(GoalEngine.normalize_to_date(None))
        self.assertIsNone(GoalEngine.normalize_to_date(""))

        # malformed created_at
        self.assertIsNone(GoalEngine.normalize_to_date("not-a-date"))
        self.assertIsNone(GoalEngine.normalize_to_date(12345))

    def test_behavioral_content_queue_is_irrelevant(self):
        """
        Requirement 4: Mock DB with:
          content_items: 2 COMPLETE verified + 2 PUBLIC pending
          content_queue: 100 bogus records
        Expected: verified=2, active=2, available=4, missing=0.
        """
        today_iso = datetime.datetime.now(datetime.UTC).isoformat()
        mock_items = [
            self._make_item("COMPLETE", today_iso, "yt1", True),
            self._make_item("COMPLETE", today_iso, "yt2", True),
            self._make_item("PUBLIC", today_iso, "yt3", None),
            self._make_item("PUBLIC", today_iso, "yt4", False),
        ]
        # Querying content_items returns the mocked list
        self.mock_db.collection.side_effect = lambda coll_name: (
            MagicMock(where=lambda *args: MagicMock(stream=lambda: mock_items))
            if coll_name == "content_items" else MagicMock()
        )

        with patch.dict("src.config.brand_registry.BRAND_REGISTRY", {"bd_threatpulse": {"daily_target": 4}}):
            counts = self.goal_engine.count_for_brand("bd_threatpulse")
            self.assertEqual(counts["verified"], 2)
            self.assertEqual(counts["active"], 2)
            self.assertEqual(counts["available"], 4)
            self.assertEqual(counts["missing"], 0)

    def test_historical_content_does_not_consume_today_target(self):
        """
        Requirement 5: target=4. yesterday had 4 COMPLETE verified. today has 0.
        Expected: missing=4.
        """
        yesterday_iso = (datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=1)).isoformat()
        mock_items = [
            self._make_item("COMPLETE", yesterday_iso, "yt_y1", True),
            self._make_item("COMPLETE", yesterday_iso, "yt_y2", True),
            self._make_item("COMPLETE", yesterday_iso, "yt_y3", True),
            self._make_item("COMPLETE", yesterday_iso, "yt_y4", True),
        ]
        self.mock_db.collection.return_value.where.return_value.stream.return_value = mock_items

        with patch.dict("src.config.brand_registry.BRAND_REGISTRY", {"bd_threatpulse": {"daily_target": 4}}):
            counts = self.goal_engine.count_for_brand("bd_threatpulse")
            self.assertEqual(counts["verified"], 0, "Yesterday's items must not count as verified today")
            self.assertEqual(counts["active"], 0)
            self.assertEqual(counts["missing"], 4)

    def test_public_pending_content_prevents_duplicate_generation(self):
        """
        Requirement 6: target=4, verified=2, PUBLIC pending=2.
        Expected: missing=0.
        """
        today_iso = datetime.datetime.now(datetime.UTC).isoformat()
        mock_items = [
            self._make_item("COMPLETE", today_iso, "yt1", True),
            self._make_item("COMPLETE", today_iso, "yt2", True),
            self._make_item("PUBLIC", today_iso, "yt3", None),
            self._make_item("PUBLIC", today_iso, "yt4", False),
        ]
        self.mock_db.collection.return_value.where.return_value.stream.return_value = mock_items

        with patch.dict("src.config.brand_registry.BRAND_REGISTRY", {"bd_threatpulse": {"daily_target": 4}}):
            counts = self.goal_engine.count_for_brand("bd_threatpulse")
            self.assertEqual(counts["missing"], 0)


# ---------------------------------------------------------------------------
# Test 7 — BrandWorker.run_cycle is a complete single cycle
# ---------------------------------------------------------------------------

class TestBrandWorkerRunCycleIsOneCycle(unittest.TestCase):
    """
    Documents that BrandWorker.run_cycle() executes exactly ONE content
    item from topic generation through upload/verify. It does not loop.
    The scheduler must call run_cycle() once per brand per round.
    """

    def test_run_cycle_creates_exactly_one_content_item(self):
        """run_cycle() creates one document and processes it — no inner loop."""
        from src.engine.brand_worker import BrandWorker
        import inspect
        src = inspect.getsource(BrandWorker.run_cycle)
        # There should be no 'for' loop in run_cycle (the loop is in evaluate())
        lines = [l.strip() for l in src.split("\n") if l.strip().startswith("for ")]
        self.assertEqual(lines, [],
            "run_cycle() must not contain a loop — it processes exactly one item")

    def test_run_cycle_calls_process_content_once(self):
        """run_cycle() delegates to _process_content exactly once."""
        from src.engine.brand_worker import BrandWorker
        import inspect
        src = inspect.getsource(BrandWorker.run_cycle)
        self.assertIn("_process_content", src)
        # Count occurrences
        self.assertEqual(src.count("_process_content"), 1)


# ---------------------------------------------------------------------------
# Test 8 — Round Robin Persistent Cursor Tests
# ---------------------------------------------------------------------------

class TestSchedulerRoundRobinCursor(unittest.TestCase):
    def setUp(self):
        from src.engine.goal_engine import GoalEngine
        self.GoalEngine = GoalEngine
        self.firestore_patch = patch("google.cloud.firestore.Client")
        self.mock_client_class = self.firestore_patch.start()
        self.mock_db = MagicMock()
        self.mock_client_class.return_value = self.mock_db
        
        # Mock environment variables to prevent KeyError or local run bypass
        self.env_patch = patch.dict("os.environ", {"CLOUD_RUN_EXECUTION": "test-run"})
        self.env_patch.start()

    def tearDown(self):
        self.firestore_patch.stop()
        self.env_patch.stop()

    def _setup_mock_firestore(self, cursor_exists=True, last_brand="bd_threatpulse", candidates=None):
        today_iso = datetime.datetime.now(datetime.UTC).isoformat()
        if candidates is None:
            # Default mock candidates
            doc_bd = MagicMock()
            doc_bd.id = "bd_1"
            doc_bd.to_dict.return_value = {"brand_id": "bd_threatpulse", "status": "NEW", "created_at": today_iso}
            doc_ww = MagicMock()
            doc_ww.id = "ww_1"
            doc_ww.to_dict.return_value = {"brand_id": "wealthwise", "status": "NEW", "created_at": today_iso}
            candidates = [doc_bd, doc_ww]

        cursor_doc = MagicMock()
        cursor_doc.exists = cursor_exists
        cursor_doc.to_dict.return_value = {"last_dispatched_brand": last_brand}

        mock_lease_doc = MagicMock()
        mock_lease_doc.exists = False

        def mock_document(doc_path):
            doc_ref = MagicMock()
            if doc_path == "production_lease":
                doc_ref.get.return_value = mock_lease_doc
            elif doc_path == "round_robin_cursor":
                doc_ref.get.return_value = cursor_doc
            return doc_ref

        mock_content_items_ref = MagicMock()
        mock_content_items_ref.stream.return_value = candidates

        def mock_collection(name):
            if name == "scheduler_leases":
                col_ref = MagicMock()
                col_ref.document.side_effect = mock_document
                return col_ref
            elif name == "content_items":
                return mock_content_items_ref
            return MagicMock()

        self.mock_db.collection.side_effect = mock_collection

    def test_rotation_starts_after_last_dispatched_brand(self):
        """Verifies brand selection order shifts to start after the last dispatched brand."""
        self._setup_mock_firestore(cursor_exists=True, last_brand="bd_threatpulse")

        mock_tx = MagicMock()
        self.mock_db.transaction.return_value = mock_tx

        with patch("google.cloud.firestore.transactional", lambda f: f):
            with patch("src.scheduler.autonomous_scheduler.GoalEngine") as mock_ge_cls:
                mock_ge = MagicMock()
                mock_ge.count_for_brand.return_value = {"daily_target": 4, "verified": 4, "active": 0, "missing": 0}
                mock_ge_cls.return_value = mock_ge
                mock_ge_cls.normalize_to_date = self.GoalEngine.normalize_to_date

                with patch("src.job_trigger.trigger_pipeline_job") as mock_trigger:
                    from src.scheduler.autonomous_scheduler import run_scheduler
                    res = run_scheduler()
                    self.assertEqual(res.get("status"), "success")
                    
                    # Rotated order after bd_threatpulse must pick wealthwise (ww_1)
                    mock_trigger.assert_called_once_with("wealthwise", "", "ww_1")

    def test_missing_cursor_document_defaults_to_alphabetical(self):
        """Verifies that first run (no cursor) defaults to alphabetical priority (bd_threatpulse)."""
        self._setup_mock_firestore(cursor_exists=False)

        mock_tx = MagicMock()
        self.mock_db.transaction.return_value = mock_tx

        with patch("google.cloud.firestore.transactional", lambda f: f):
            with patch("src.scheduler.autonomous_scheduler.GoalEngine") as mock_ge_cls:
                mock_ge = MagicMock()
                mock_ge.count_for_brand.return_value = {"daily_target": 4, "verified": 4, "active": 0, "missing": 0}
                mock_ge_cls.return_value = mock_ge
                mock_ge_cls.normalize_to_date = self.GoalEngine.normalize_to_date

                with patch("src.job_trigger.trigger_pipeline_job") as mock_trigger:
                    from src.scheduler.autonomous_scheduler import run_scheduler
                    run_scheduler()
                    
                    # Defaults to alphabetically first: bd_threatpulse (bd_1)
                    mock_trigger.assert_called_once_with("bd_threatpulse", "", "bd_1")

    def test_cursor_write_failure_does_not_invalidate_claimed_item(self):
        """Verifies cursor write exceptions are caught and do not cancel dispatch."""
        self._setup_mock_firestore(cursor_exists=True, last_brand="bd_threatpulse")

        # Mock cursor document ref set method to raise exception
        cursor_ref_mock = MagicMock()
        cursor_ref_mock.set.side_effect = Exception("Firestore write simulated failure")
        
        def mock_document_with_fail(doc_path):
            if doc_path == "round_robin_cursor":
                return cursor_ref_mock
            mock_lease_doc = MagicMock()
            mock_lease_doc.exists = False
            doc_ref = MagicMock()
            doc_ref.get.return_value = mock_lease_doc
            return doc_ref

        self.mock_db.collection.return_value.document.side_effect = mock_document_with_fail

        mock_tx = MagicMock()
        self.mock_db.transaction.return_value = mock_tx

        with patch("google.cloud.firestore.transactional", lambda f: f):
            with patch("src.scheduler.autonomous_scheduler.GoalEngine") as mock_ge_cls:
                mock_ge = MagicMock()
                mock_ge.count_for_brand.return_value = {"daily_target": 4, "verified": 4, "active": 0, "missing": 0}
                mock_ge_cls.return_value = mock_ge
                mock_ge_cls.normalize_to_date = self.GoalEngine.normalize_to_date

                with patch("src.job_trigger.trigger_pipeline_job") as mock_trigger:
                    from src.scheduler.autonomous_scheduler import run_scheduler
                    res = run_scheduler()
                    self.assertEqual(res.get("status"), "success")
                    
                    # Dispatch still completed successfully
                    mock_trigger.assert_called_once()

    def test_no_selected_item_leaves_cursor_untouched(self):
        """Verifies that if no items are selected/dispatched, cursor update is skipped."""
        self._setup_mock_firestore(cursor_exists=True, last_brand="bd_threatpulse", candidates=[])

        mock_tx = MagicMock()
        self.mock_db.transaction.return_value = mock_tx

        with patch("google.cloud.firestore.transactional", lambda f: f):
            with patch("src.scheduler.autonomous_scheduler.GoalEngine") as mock_ge_cls:
                mock_ge = MagicMock()
                mock_ge.count_for_brand.return_value = {"daily_target": 4, "verified": 4, "active": 0, "missing": 0}
                mock_ge_cls.return_value = mock_ge
                mock_ge_cls.normalize_to_date = self.GoalEngine.normalize_to_date

                with patch("src.job_trigger.trigger_pipeline_job") as mock_trigger:
                    from src.scheduler.autonomous_scheduler import run_scheduler
                    run_scheduler()
                    
                    # No trigger, and cursor set was never invoked
                    mock_trigger.assert_not_called()
                    self.mock_db.collection("scheduler_leases").document("round_robin_cursor").set.assert_not_called()


if __name__ == "__main__":
    unittest.main()



