"""
Tier 1 — Unit: Metrics Service
Fully mocked Firestore. Zero GCP calls.
"""
import pytest
from unittest.mock import patch, MagicMock


@patch("src.engine.metrics_service.firestore")
def test_increment_calls_firestore_set(mock_fs):
    mock_db = MagicMock()
    mock_fs.Client.return_value = mock_db
    mock_fs.Increment.return_value = "INCREMENT_SENTINEL"
    from src.engine.metrics_service import MetricsService
    svc = MetricsService()
    svc.increment_metric("bd_threatpulse", "2026-08-07", "published")
    mock_db.collection.assert_called_with("production_metrics")
    doc_ref = mock_db.collection().document().collection().document()
    doc_ref.set.assert_called_once()
    call_args = doc_ref.set.call_args
    assert call_args.kwargs.get("merge") is True or call_args.args[1] is True


@patch("src.engine.metrics_service.firestore")
def test_update_metrics_uses_merge(mock_fs):
    mock_db = MagicMock()
    mock_fs.Client.return_value = mock_db
    from src.engine.metrics_service import MetricsService
    svc = MetricsService()
    svc.update_metrics("wealthwise", "2026-08-07", {"published": 4, "failed": 0})
    doc_ref = mock_db.collection().document().collection().document()
    call_args = doc_ref.set.call_args
    assert call_args.kwargs.get("merge") is True or call_args.args[1] is True


@patch("src.engine.metrics_service.firestore")
def test_document_path_is_brand_scoped(mock_fs):
    mock_db = MagicMock()
    mock_fs.Client.return_value = mock_db
    from src.engine.metrics_service import MetricsService
    svc = MetricsService()
    svc.increment_metric("philosophy", "2026-08-07", "published")
    calls = [str(c) for c in mock_db.collection.call_args_list]
    assert any("production_metrics" in c for c in calls)
    doc_calls = [str(c) for c in mock_db.collection().document.call_args_list]
    assert any("philosophy" in c for c in doc_calls)


@patch("src.engine.metrics_service.firestore")
def test_firestore_error_does_not_raise(mock_fs):
    mock_db = MagicMock()
    mock_fs.Client.return_value = mock_db
    mock_db.collection.side_effect = Exception("Firestore unavailable")
    from src.engine.metrics_service import MetricsService
    svc = MetricsService()
    # Should not raise — errors are caught and logged
    try:
        svc.increment_metric("kids_universe", "2026-08-07", "published")
    except Exception:
        pytest.fail("MetricsService should not propagate Firestore errors")


@patch("src.engine.metrics_service.firestore")
def test_four_brand_ids_produce_four_paths(mock_fs):
    mock_db = MagicMock()
    mock_fs.Client.return_value = mock_db
    from src.engine.metrics_service import MetricsService
    svc = MetricsService()
    brands = ["bd_threatpulse", "wealthwise", "kids_universe", "philosophy"]
    for b in brands:
        svc.increment_metric(b, "2026-08-07", "published")
    doc_calls = [str(c) for c in mock_db.collection().document.call_args_list]
    for b in brands:
        assert any(b in c for c in doc_calls), f"Brand {b} not in document path calls"
