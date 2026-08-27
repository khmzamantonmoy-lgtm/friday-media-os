"""
ai_request_manager.py

Centralized AI Request Manager for FRIDAY Media OS.
Enforces sequential execution, backoff, retry logic, and fallback telemetry.
Uses Vertex AI (IAM) as the primary production architecture.
"""

import os
import time
import logging
import threading
from google import genai

logger = logging.getLogger("ai_request_manager")

class AIRequestManager:
    _instance = None
    _lock = threading.Lock()
    _semaphore = threading.Semaphore(1)  # Enforce max 1 concurrent request per container process

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(AIRequestManager, cls).__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if self._initialized:
            return
        
        self.keys = []  # Vertex AI uses IAM credentials, no API keys needed
        self.metrics = {
            "quota_failures": 0,
            "successful_recoveries": 0
        }
        self._initialized = True
        logger.info("AIRequestManager initialized with Vertex AI (IAM) as primary production provider.")

    def get_client(self):
        """Returns a genai.Client instance configured for Vertex AI (IAM)."""
        os.environ["GOOGLE_CLOUD_PROJECT"] = "friday-media-prod"
        os.environ["GCP_PROJECT_ID"] = "friday-media-prod"
        
        return genai.Client(
            vertexai=True,
            project="friday-media-prod",
            location="us-central1"
        )

    def rotate_key(self):
        return False

    def execute(self, operation_fn):
        """Executes operation with strict in-process serialization and robust exponential backoff retries."""
        with self._semaphore:
            max_retries = 8  # Sufficient to clear standard 60-second quota windows
            client = self.get_client()
            
            logger.info("VERTEX_REQUEST_ADMITTED")
            start_time = time.time()
            
            for attempt in range(max_retries):
                try:
                    response = operation_fn(client)
                    duration = time.time() - start_time
                    logger.info(f"VERTEX_REQUEST_COMPLETED: duration={duration:.2f}s")
                    if attempt > 0:
                        self.metrics["successful_recoveries"] += 1
                        logger.info(f"Successfully recovered from Vertex AI quota limit on retry {attempt+1}")
                    return response
                except Exception as e:
                    err_msg = str(e).upper()
                    # Catch quota / rate limit errors
                    if "429" in err_msg or "RESOURCE_EXHAUSTED" in err_msg or "QUOTA" in err_msg:
                        self.metrics["quota_failures"] += 1
                        
                        # Exponential backoff: 6s, 12s, 24s, 48s... + jitter
                        wait_time = ((2 ** attempt) * 6) + (time.time() % 3)
                        logger.warning(
                            f"VERTEX_REQUEST_THROTTLED: local retry {attempt+1}/{max_retries} in {wait_time:.2f}s... Error: {e}"
                        )
                        time.sleep(wait_time)
                    else:
                        raise e
            
            raise RuntimeError("Vertex AI rate limit retries exhausted. Operation failed.")

    def get_summary(self):
        return self.metrics
