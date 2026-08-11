import os
import logging

try:
    import chromadb
    CHROMA_AVAILABLE = True
except ImportError:
    CHROMA_AVAILABLE = False

try:
    from vertexai.language_models import TextEmbeddingModel
    VERTEX_EMBEDDING_AVAILABLE = True
except ImportError:
    VERTEX_EMBEDDING_AVAILABLE = False

logger = logging.getLogger(__name__)


def _get_embedding_vertex(text: str) -> list[float]:
    """Embed using Vertex AI textembedding-gecko@003 via AIRequestManager."""
    from src.config.ai_request_manager import AIRequestManager
    import time
    ai_manager = AIRequestManager()
    def _op(client):
        logger.info("EMBEDDING_CALL_ADMITTED")
        start_time = time.time()
        model = TextEmbeddingModel.from_pretrained("textembedding-gecko@003")
        embeddings = model.get_embeddings([text])
        duration = time.time() - start_time
        logger.info(f"EMBEDDING_CALL_COMPLETED: duration={duration:.2f}s")
        return embeddings[0].values
    return ai_manager.execute(_op)


def _get_embedding_genai(text: str) -> list[float]:
    """Fallback: embed using google-genai SDK (text-embedding-004) via AIRequestManager."""
    from src.config.ai_request_manager import AIRequestManager
    import time
    ai_manager = AIRequestManager()
    def _op(client):
        logger.info("EMBEDDING_CALL_ADMITTED")
        start_time = time.time()
        response = client.models.embed_content(
            model="text-embedding-004",
            contents=text,
        )
        duration = time.time() - start_time
        logger.info(f"EMBEDDING_CALL_COMPLETED: duration={duration:.2f}s")
        return response.embeddings[0].values
    return ai_manager.execute(_op)


def get_embedding(text: str) -> list[float]:
    """Returns a text embedding, preferring Vertex AI, falling back to genai."""
    if VERTEX_EMBEDDING_AVAILABLE:
        try:
            return _get_embedding_vertex(text)
        except Exception as e:
            logger.warning(f"Vertex embedding failed, falling back to genai: {e}")
    return _get_embedding_genai(text)


class SemanticMemory:
    """
    Per-brand semantic topic memory backed by ChromaDB.

    Duplicate detection logic:
      similarity < 0.55   → clearly unique  → allow
      similarity > 0.75   → clearly duplicate → reject
      0.55 <= sim <= 0.75 → gray zone → delegate to Gemini judge
    """

    def __init__(self, brand_id: str):
        self.brand_id = brand_id
        if CHROMA_AVAILABLE:
            self.chroma = chromadb.PersistentClient(path="/tmp/friday_chroma")
            self.collection = self.chroma.get_or_create_collection(
                name=f"brand_{brand_id}",
                metadata={"hnsw:space": "cosine"},
            )
        else:
            self.chroma = None
            self.collection = None

    def check_duplicate(self, topic: str) -> bool:
        """Returns True if `topic` is a semantic duplicate of a stored topic."""
        if not CHROMA_AVAILABLE or self.collection is None:
            logger.warning("ChromaDB unavailable; semantic duplicate check skipped.")
            return False

        if self.collection.count() == 0:
            return False

        embedding = get_embedding(topic)
        results = self.collection.query(
            query_embeddings=[embedding],
            n_results=1,
            include=["distances", "documents"],
        )

        if not results["distances"] or not results["distances"][0]:
            return False

        # chromadb cosine space returns cosine distance in [0, 2].
        # cosine similarity = 1 - distance (for normalized vectors, distance in [0,1])
        distance = results["distances"][0][0]
        similarity = max(0.0, 1.0 - distance)
        matched_topic = results["documents"][0][0] if results["documents"][0] else ""

        logger.info(
            f"[{self.brand_id}] Similarity={similarity:.3f} | "
            f"new='{topic[:60]}' | existing='{matched_topic[:60]}'"
        )

        if similarity < 0.55:
            return False
        elif similarity > 0.75:
            logger.warning(f"Rejected duplicate topic (sim={similarity:.3f}): '{topic[:80]}'")
            return True
        else:
            # Gray zone: call Gemini as a semantic judge
            is_dup = self._gemini_judge(topic, matched_topic)
            if is_dup:
                logger.warning(f"Gemini judge rejected duplicate (sim={similarity:.3f}): '{topic[:80]}'")
            return is_dup

    def _gemini_judge(self, new_topic: str, old_topic: str) -> bool:
        """Use Gemini to decide if two topics are conceptually the same."""
        from src.config.ai_request_manager import AIRequestManager
        prompt = (
            "Are these two video topics essentially the same idea? "
            "Reply with exactly YES or NO, nothing else.\n"
            f"Topic A: {new_topic}\n"
            f"Topic B: {old_topic}"
        )
        try:
            ai_manager = AIRequestManager()
            def _op(client):
                response = client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=prompt,
                )
                return response.text.strip().upper().startswith("YES")
            return ai_manager.execute(_op)
        except Exception as e:
            logger.error(f"Gemini judge failed: {e}. Defaulting to NOT duplicate.")
            return False

    def add_memory(self, doc_id: str, topic: str) -> None:
        """Store a successfully published topic in the embedding store."""
        if not CHROMA_AVAILABLE or self.collection is None:
            return
        try:
            embedding = get_embedding(topic)
            self.collection.add(
                embeddings=[embedding],
                documents=[topic],
                ids=[doc_id],
            )
            logger.info(f"[{self.brand_id}] Added topic to semantic memory: '{topic[:80]}'")
        except Exception as e:
            logger.error(f"Failed to add topic to semantic memory: {e}")
