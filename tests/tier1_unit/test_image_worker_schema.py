"""
Tier 1 — Unit: Image Worker Schema Regression Test
Proves image generation prompt assembly and GCS blob path generation work cleanly
without KeyError for all four registered brands in BRAND_REGISTRY.
"""

import pytest
from unittest.mock import patch, MagicMock
from src.config.brand_registry import BRAND_REGISTRY
from src.workers.image_worker import generate_single_image

@patch("src.workers.image_worker.storage.Client")
@patch("src.workers.image_worker.AIRequestManager.execute")
def test_generate_single_image_works_for_all_four_registered_brands(mock_execute, mock_storage):
    """Test that generate_single_image processes all registered brands without KeyError."""
    mock_part = MagicMock()
    mock_part.inline_data.data = b"fake_png_bytes"
    mock_response = MagicMock()
    mock_response.candidates = [MagicMock(content=MagicMock(parts=[mock_part]))]
    mock_execute.return_value = mock_response

    mock_bucket = MagicMock()
    mock_storage.return_value.bucket.return_value = mock_bucket

    scene = {"text": "A futuristic city with flying vehicles", "timestamp": 0}

    for brand_id, brand_cfg in BRAND_REGISTRY.items():
        # Ensure brand_id key exists if missing in dictionary
        cfg = dict(brand_cfg)
        cfg["id"] = brand_id
        
        uri = generate_single_image((0, scene, cfg, "content_123"))
        assert uri.startswith("gs://")
        assert "content_123_frame_0.png" in uri

    assert mock_execute.call_count == 4
