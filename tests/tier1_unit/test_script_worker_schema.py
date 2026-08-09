"""
Tier 1 — Unit: Script Worker Schema Regression Test
Proves script generation prompt formatting works cleanly without KeyError
for all four registered brands in BRAND_REGISTRY.
"""

import pytest
from unittest.mock import patch, MagicMock
from src.config.brand_registry import BRAND_REGISTRY
from src.workers.script_worker import generate_script

@patch("src.workers.script_worker.AIRequestManager.execute")
def test_generate_script_works_for_all_four_registered_brands(mock_execute):
    """Test that generate_script generates prompts cleanly for all registered brands without KeyError."""
    mock_response = MagicMock()
    mock_response.text = '{"hook": "Test Hook", "narration": "Test Narration", "visual_prompts": [{"text": "Test Scene", "timestamp": 0}]}'
    mock_execute.return_value = mock_response

    for brand_id, brand_cfg in BRAND_REGISTRY.items():
        res = generate_script(brand_cfg, "Test Topic")
        assert res["hook"] == "Test Hook"
        assert res["narration"] == "Test Narration"
        assert len(res["visual_prompts"]) == 1

    assert mock_execute.call_count == 4
