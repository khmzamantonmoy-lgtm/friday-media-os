"""
Tier 2 — Integration: Cross-System Consistency
Validates data contract alignment between components.
No live GCP calls.
"""
import pytest
import inspect


def test_goal_engine_queries_content_items():
    """GoalEngine must query content_items, not content_queue."""
    from src.engine import goal_engine
    src_code = inspect.getsource(goal_engine.GoalEngine.count_for_brand)
    assert "content_items" in src_code, "GoalEngine must query content_items collection"


def test_brand_worker_writes_to_content_items():
    """BrandWorker must create docs in content_items."""
    from src.engine import brand_worker
    src_code = inspect.getsource(brand_worker.BrandWorker.run_cycle)
    assert "content_items" in src_code, "BrandWorker must write to content_items"


def test_scheduler_queries_content_items_for_housekeeping():
    """Scheduler housekeeping must target content_items for stuck-item detection."""
    from src.scheduler import autonomous_scheduler
    src_code = inspect.getsource(autonomous_scheduler.run_scheduler)
    assert "content_items" in src_code, "Scheduler must query content_items for housekeeping"


def test_metrics_service_path_matches_dashboard():
    """Metrics path must use production_metrics/{brand_id}/daily/{date}."""
    from src.engine import metrics_service
    src_code = inspect.getsource(metrics_service.MetricsService.increment_metric)
    assert "production_metrics" in src_code
    assert "daily" in src_code


def test_verifier_writes_youtube_verified_field():
    """PublicationVerifier must write youtube_verified=True on success."""
    from src.engine import publication_verifier
    src_code = inspect.getsource(publication_verifier.PublicationVerifier.verify_status)
    assert "youtube_verified" in src_code


def test_brand_registry_daily_target_is_four():
    """All 4 brands must have daily_target=4."""
    from src.config.brand_registry import BRAND_REGISTRY
    for brand_id, cfg in BRAND_REGISTRY.items():
        assert cfg.get("daily_target") == 4, (
            f"Brand {brand_id} daily_target is {cfg.get('daily_target')}, expected 4"
        )


def test_state_machine_complete_value_matches_goal_engine():
    """GoalEngine checks status == 'COMPLETE'; ContentState.COMPLETE.value must match."""
    from src.engine.state_machine import ContentState
    from src.engine import goal_engine
    src_code = inspect.getsource(goal_engine.GoalEngine.count_for_brand)
    assert ContentState.COMPLETE.value in src_code, (
        f"GoalEngine must check for '{ContentState.COMPLETE.value}'"
    )


def test_brand_registry_all_four_brands_present():
    """Exactly 4 brands must be registered."""
    from src.config.brand_registry import BRAND_REGISTRY
    expected = {"bd_threatpulse", "wealthwise", "kids_universe", "philosophy"}
    assert set(BRAND_REGISTRY.keys()) == expected, (
        f"Expected brands {expected}, got {set(BRAND_REGISTRY.keys())}"
    )


def test_verifier_requires_brand_id_argument():
    """PublicationVerifier.verify must accept brand_id as a parameter."""
    import inspect
    from src.engine.publication_verifier import PublicationVerifier
    sig = inspect.signature(PublicationVerifier.verify)
    assert "brand_id" in sig.parameters, "verify() must accept brand_id parameter"


def test_scheduler_imports_brand_registry():
    """Scheduler must iterate brands from BRAND_REGISTRY, not a hardcoded list."""
    from src.scheduler import autonomous_scheduler
    src_code = inspect.getsource(autonomous_scheduler.run_scheduler)
    assert "BRAND_REGISTRY" in src_code, "Scheduler must use BRAND_REGISTRY for brand iteration"
