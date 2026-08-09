"""
Tier 2 — Integration: AI Provider Unification Regression Tests
Proves BrandWorker and SemanticMemory use AIRequestManager (Vertex AI / IAM)
and operate cleanly without GEMINI_API_KEY environment variables.
"""

import os
import pytest
from unittest.mock import patch, MagicMock

def test_no_direct_genai_client_in_production_paths():
    """Verify that brand_worker.py and semantic_memory.py do not directly instantiate genai.Client()."""
    with open("src/engine/brand_worker.py", "r") as f:
        bw_code = f.read()
    with open("src/engine/semantic_memory.py", "r") as f:
        sm_code = f.read()
        
    assert "genai.Client()" not in bw_code, "brand_worker.py contains unconfigured genai.Client()"
    assert "genai.Client()" not in sm_code, "semantic_memory.py contains unconfigured genai.Client()"

@patch("src.config.ai_request_manager.AIRequestManager.execute")
@patch("src.engine.brand_worker.SemanticMemory")
@patch("src.engine.brand_worker.firestore")
def test_brand_worker_topic_generation_uses_ai_request_manager(mock_fs, mock_mem_cls, mock_execute, monkeypatch):
    """Verify BrandWorker._generate_topic uses AIRequestManager without GEMINI_API_KEY."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    
    mock_execute.return_value = "AI Generated Topic"
    mock_mem = MagicMock()
    mock_mem.check_duplicate.return_value = False
    
    from src.engine.brand_worker import BrandWorker
    worker = BrandWorker()
    
    brand = {"id": "bd_threatpulse", "persona": "security analyst"}
    topic = worker._generate_topic(brand, mock_mem)
    
    assert topic == "AI Generated Topic"
    assert mock_execute.call_count == 1

@patch("src.config.ai_request_manager.AIRequestManager.execute")
def test_semantic_memory_judge_uses_ai_request_manager(mock_execute, monkeypatch):
    """Verify SemanticMemory._gemini_judge uses AIRequestManager without GEMINI_API_KEY."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    
    mock_execute.return_value = True
    
    from src.engine.semantic_memory import SemanticMemory
    mem = SemanticMemory("bd_threatpulse")
    is_dup = mem._gemini_judge("Topic A", "Topic B")
    
    assert is_dup is True
    assert mock_execute.call_count == 1

def test_ai_request_manager_returns_vertex_client(monkeypatch):
    """Verify AIRequestManager initializes genai.Client with vertexai=True."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    
    with patch("src.config.ai_request_manager.genai.Client") as mock_genai_client:
        from src.config.ai_request_manager import AIRequestManager
        mgr = AIRequestManager()
        client = mgr.get_client()
        mock_genai_client.assert_called_once_with(
            vertexai=True,
            project="friday-media-prod",
            location="us-central1"
        )
