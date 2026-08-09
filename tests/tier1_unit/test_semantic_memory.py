"""
Tier 1 — Unit: Semantic Memory
ChromaDB and embedding functions fully mocked.
"""
import pytest
from unittest.mock import patch, MagicMock

def _mock_collection(count=1, distance=None):
    col = MagicMock()
    col.count.return_value = count
    if distance is not None:
        col.query.return_value = {
            "distances": [[distance]],
            "documents": [["Existing topic about cybersecurity"]],
        }
    else:
        col.query.return_value = {"distances": [[]], "documents": [[]]}
    return col

@patch("src.engine.semantic_memory.CHROMA_AVAILABLE", True)
@patch("src.engine.semantic_memory.get_embedding", return_value=[0.1] * 768)
def test_empty_collection_never_duplicate(mock_embed):
    col = _mock_collection(count=0)
    from src.engine.semantic_memory import SemanticMemory
    mem = SemanticMemory("bd_threatpulse")
    mem.collection = col
    assert mem.check_duplicate("New topic") is False

@patch("src.engine.semantic_memory.CHROMA_AVAILABLE", True)
@patch("src.engine.semantic_memory.get_embedding", return_value=[0.1] * 768)
def test_low_similarity_accepted(mock_embed):
    col = _mock_collection(count=5, distance=0.65)  # similarity = 0.35
    from src.engine.semantic_memory import SemanticMemory
    mem = SemanticMemory("wealthwise")
    mem.collection = col
    assert mem.check_duplicate("Cooking recipes") is False

@patch("src.engine.semantic_memory.CHROMA_AVAILABLE", True)
@patch("src.engine.semantic_memory.get_embedding", return_value=[0.1] * 768)
def test_high_similarity_rejected(mock_embed):
    col = _mock_collection(count=5, distance=0.1)  # similarity = 0.90
    from src.engine.semantic_memory import SemanticMemory
    mem = SemanticMemory("bd_threatpulse")
    mem.collection = col
    result = mem.check_duplicate("Zero Trust Security Frameworks")
    assert result is True

@patch("src.engine.semantic_memory.CHROMA_AVAILABLE", True)
@patch("src.engine.semantic_memory.get_embedding", return_value=[0.1] * 768)
def test_gray_zone_invokes_gemini(mock_embed):
    col = _mock_collection(count=5, distance=0.4)  # similarity = 0.60 -> gray zone
    from src.engine.semantic_memory import SemanticMemory
    mem = SemanticMemory("philosophy")
    mem.collection = col
    with patch.object(mem, "_gemini_judge", return_value=False) as mock_judge:
        result = mem.check_duplicate("Stoic wisdom on resilience")
        mock_judge.assert_called_once()

@patch("src.engine.semantic_memory.CHROMA_AVAILABLE", True)
@patch("src.engine.semantic_memory.get_embedding", return_value=[0.1] * 768)
def test_gemini_yes_means_duplicate(mock_embed):
    col = _mock_collection(count=5, distance=0.4)
    from src.engine.semantic_memory import SemanticMemory
    mem = SemanticMemory("philosophy")
    mem.collection = col
    with patch.object(mem, "_gemini_judge", return_value=True):
        assert mem.check_duplicate("Stoic topic") is True

@patch("src.engine.semantic_memory.CHROMA_AVAILABLE", True)
@patch("src.engine.semantic_memory.get_embedding", return_value=[0.1] * 768)
def test_gemini_no_means_unique(mock_embed):
    col = _mock_collection(count=5, distance=0.4)
    from src.engine.semantic_memory import SemanticMemory
    mem = SemanticMemory("philosophy")
    mem.collection = col
    with patch.object(mem, "_gemini_judge", return_value=False):
        assert mem.check_duplicate("Different topic") is False

@patch("src.engine.semantic_memory.CHROMA_AVAILABLE", True)
@patch("src.engine.semantic_memory.get_embedding", return_value=[0.1] * 768)
def test_gemini_exception_defaults_false(mock_embed):
    col = _mock_collection(count=5, distance=0.4)
    from src.engine.semantic_memory import SemanticMemory
    mem = SemanticMemory("philosophy")
    mem.collection = col
    with patch("google.genai.Client") as mock_genai:
        mock_genai.return_value.models.generate_content.side_effect = Exception("Gemini down")
        result = mem.check_duplicate("Topic")
        assert result is False

@patch("src.engine.semantic_memory.CHROMA_AVAILABLE", True)
@patch("src.engine.semantic_memory.get_embedding", return_value=[0.1] * 768)
def test_add_memory_calls_collection_add(mock_embed):
    col = MagicMock()
    from src.engine.semantic_memory import SemanticMemory
    mem = SemanticMemory("kids_universe")
    mem.collection = col
    mem.add_memory("doc_001", "Why is the sky blue?")
    col.add.assert_called_once()
    call_kwargs = str(col.add.call_args)
    assert "doc_001" in call_kwargs

@patch("src.engine.semantic_memory.CHROMA_AVAILABLE", True)
@patch("src.engine.semantic_memory.get_embedding", return_value=[0.1] * 768)
def test_add_memory_uses_embedding(mock_embed):
    col = MagicMock()
    from src.engine.semantic_memory import SemanticMemory
    mem = SemanticMemory("kids_universe")
    mem.collection = col
    mem.add_memory("doc_002", "Whale communication")
    mock_embed.assert_called()

@patch("src.engine.semantic_memory.CHROMA_AVAILABLE", True)
def test_four_brands_use_separate_collections():
    with patch("chromadb.PersistentClient") as mock_client_cls:
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.get_or_create_collection.return_value = MagicMock(count=MagicMock(return_value=0))
        from src.engine.semantic_memory import SemanticMemory
        brands = ["bd_threatpulse", "wealthwise", "kids_universe", "philosophy"]
        for b in brands:
            SemanticMemory(b)
        calls = [str(c) for c in mock_client.get_or_create_collection.call_args_list]
        for b in brands:
            assert any(f"brand_{b}" in c for c in calls), f"Collection brand_{b} not created"

@patch("src.engine.semantic_memory.CHROMA_AVAILABLE", False)
def test_chromadb_unavailable_skips_check():
    from src.engine.semantic_memory import SemanticMemory
    mem = SemanticMemory("bd_threatpulse")
    mem.collection = None
    result = mem.check_duplicate("Any topic")
    assert result is False

@patch("src.engine.semantic_memory.CHROMA_AVAILABLE", True)
@patch("src.engine.semantic_memory.get_embedding", return_value=[0.1] * 768)
def test_similarity_clamped_to_zero(mock_embed):
    col = _mock_collection(count=5, distance=1.5)  # similarity = max(0, 1.0 - 1.5) = 0.0
    from src.engine.semantic_memory import SemanticMemory
    mem = SemanticMemory("wealthwise")
    mem.collection = col
    result = mem.check_duplicate("Topic")
    assert result is False
