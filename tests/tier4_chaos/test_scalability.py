"""
Tier 4 — Chaos: Scalability & Expansion Simulation
Simulates future multi-brand scaling (8, 16, 32 brands).
All mocked. Zero GCP calls.
"""
import pytest
from unittest.mock import patch, MagicMock

def generate_mock_brands(count):
    return {
        f"brand_{i:02d}": {
            "brand_id": f"brand_{i:02d}",
            "brand_name": f"Brand {i}",
            "daily_target": 4,
            "voice_id": "en-US-Neural2-I"
        }
        for i in range(count)
    }

@patch("src.engine.retry_manager.time.sleep")
@patch("src.engine.goal_engine.BrandWorker")
@patch("src.engine.goal_engine.firestore")
def test_goal_engine_handles_8_brands(mock_fs, MockWorker, mock_sleep):
    mock_fs.Client.return_value = MagicMock()
    mock_instance = MockWorker.return_value
    brands_8 = generate_mock_brands(8)
    with patch("src.engine.goal_engine.BRAND_REGISTRY", brands_8):
        from src.engine.goal_engine import GoalEngine
        engine = GoalEngine()
        for b_id in brands_8.keys():
            engine.evaluate(b_id)
    assert mock_instance.run_cycle.call_count == 32

@patch("src.engine.retry_manager.time.sleep")
@patch("src.engine.goal_engine.BrandWorker")
@patch("src.engine.goal_engine.firestore")
def test_goal_engine_handles_16_brands(mock_fs, MockWorker, mock_sleep):
    mock_fs.Client.return_value = MagicMock()
    mock_instance = MockWorker.return_value
    brands_16 = generate_mock_brands(16)
    with patch("src.engine.goal_engine.BRAND_REGISTRY", brands_16):
        from src.engine.goal_engine import GoalEngine
        engine = GoalEngine()
        for b_id in brands_16.keys():
            engine.evaluate(b_id)
    assert mock_instance.run_cycle.call_count == 64

@patch("src.engine.retry_manager.time.sleep")
@patch("src.engine.goal_engine.BrandWorker")
@patch("src.engine.goal_engine.firestore")
def test_goal_engine_handles_32_brands(mock_fs, MockWorker, mock_sleep):
    mock_fs.Client.return_value = MagicMock()
    mock_instance = MockWorker.return_value
    brands_32 = generate_mock_brands(32)
    with patch("src.engine.goal_engine.BRAND_REGISTRY", brands_32):
        from src.engine.goal_engine import GoalEngine
        engine = GoalEngine()
        for b_id in brands_32.keys():
            engine.evaluate(b_id)
    assert mock_instance.run_cycle.call_count == 128

@patch("src.engine.retry_manager.time.sleep")
@patch("src.engine.goal_engine.BrandWorker")
@patch("src.engine.goal_engine.firestore")
def test_brand_isolation_under_scale(mock_fs, MockWorker, mock_sleep):
    """When Brand 5 crashes in a 16-brand batch, all other 15 brands still finish."""
    mock_fs.Client.return_value = MagicMock()
    mock_instance = MockWorker.return_value
    brands_16 = generate_mock_brands(16)
    call_records = []
    
    def side_effect(brand_id):
        call_records.append(brand_id)
        if brand_id == "brand_05":
            raise Exception("Brand 05 unexpected crash")

    mock_instance.run_cycle.side_effect = side_effect

    with patch("src.engine.goal_engine.BRAND_REGISTRY", brands_16):
        from src.engine.goal_engine import GoalEngine
        engine = GoalEngine()
        for b_id in brands_16.keys():
            engine.evaluate(b_id)

    # All 16 brands were attempted
    assert "brand_15" in call_records
    assert "brand_05" in call_records
    assert len(set(call_records)) == 16

@patch("src.engine.semantic_memory.CHROMA_AVAILABLE", True)
@patch("src.engine.semantic_memory.chromadb")
def test_semantic_memory_separate_per_brand_scale(mock_chroma):
    mock_client = MagicMock()
    mock_chroma.PersistentClient.return_value = mock_client
    from src.engine.semantic_memory import SemanticMemory
    brands_16 = generate_mock_brands(16)
    for b_id in brands_16.keys():
        SemanticMemory(b_id)
    assert mock_client.get_or_create_collection.call_count == 16

@patch("src.engine.metrics_service.firestore")
def test_metrics_service_scales_to_32_brands(mock_fs):
    mock_db = MagicMock()
    mock_fs.Client.return_value = mock_db
    from src.engine.metrics_service import MetricsService
    svc = MetricsService()
    brands_32 = generate_mock_brands(32)
    for b_id in brands_32.keys():
        svc.increment_metric(b_id, "2026-08-07", "published")
    assert mock_db.collection.call_count >= 32
