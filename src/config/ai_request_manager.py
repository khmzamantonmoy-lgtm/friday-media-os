"""
ai_request_manager.py

Centralized AI Request Manager for FRIDAY Media OS.
Enforces sequential execution, API key rotation, backoff, jitter, 
circuit breaking, and centralized telemetry.
"""

import os
import time
import logging
import threading
from google import genai
from google.genai import types

logger = logging.getLogger("ai_request_manager")

class AIRequestManager:
    _instance = None
    _lock = threading.Lock()
    _semaphore = threading.Semaphore(1) # Priority 1: Max 1 concurrent request

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(AIRequestManager, cls).__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if self._initialized:
            return
        
        self.keys = self._load_keys()
        self.current_key_index = 0
        self.circuit_open = False
        self.circuit_trip_time = 0
        self.metrics = {
            "failover_count": 0,
            "quota_failures": 0,
            "successful_recoveries": 0,
            "circuit_trips": 0
        }
        self._initialized = True
        
        if not self.keys:
            logger.warning("No Gemini API keys found. System will fall back to Vertex AI (IAM).")

    def _load_keys(self):
        keys = []
        for var in ["PRIMARY_KEY", "SECONDARY_KEY", "TERTIARY_KEY"]:
            val = os.environ.get(var)
            if val:
                keys.append(val)
        return keys

    def get_client(self):
        if not self.keys:
            # Fallback to Vertex AI (IAM)
            os.environ["GOOGLE_CLOUD_PROJECT"] = "friday-media-prod"
            os.environ["GCP_PROJECT_ID"] = "friday-media-prod"
            return genai.Client(
                vertexai=True,
                project="friday-media-prod",
                location="us-central1"
            )
        
        # Use direct API Key (Vertex AI disabled)
        return genai.Client(api_key=self.keys[self.current_key_index], vertexai=False)

    def rotate_key(self):
        if not self.keys or len(self.keys) <= 1:
            return False
        self.current_key_index = (self.current_key_index + 1) % len(self.keys)
        self.metrics["failover_count"] += 1
        logger.info(f"Rotating to Gemini API Key #{self.current_key_index + 1}")
        return True

    def execute(self, operation_fn):
        """Executes operation with strict concurrency control, backoff, and rotation."""
        if self.circuit_open:
            if time.time() - self.circuit_trip_time > 300: # 5 min reset
                logger.info("Circuit breaker resetting.")
                self.circuit_open = False
            else:
                raise RuntimeError("Circuit breaker is OPEN. AI services suspended.")

        with self._semaphore: # Priority 1: Max 1 concurrent request
            max_retries = 3
            
            keys_tried = 0
            total_keys = len(self.keys) if self.keys else 1
            
            while keys_tried < total_keys:
                client = self.get_client()
                
                for attempt in range(max_retries):
                    try:
                        response = operation_fn(client)
                        return response
                    except Exception as e:
                        err_msg = str(e).upper()
                        if "429" in err_msg or "RESOURCE_EXHAUSTED" in err_msg:
                            self.metrics["quota_failures"] += 1
                            # Backoff + Jitter
                            wait_time = ((2 ** attempt) * 5) + (time.time() % 2)
                            logger.warning(f"Quota exhausted. Retry {attempt+1} in {wait_time:.2f}s...")
                            time.sleep(wait_time)
                        else:
                            raise e
                
                # If retries exhausted, rotate key
                if self.rotate_key():
                    keys_tried += 1
                    logger.warning("Retries exhausted for key. Rotating...")
                else:
                    self.circuit_open = True
                    self.circuit_trip_time = time.time()
                    self.metrics["circuit_trips"] += 1
                    raise RuntimeError("All API keys exhausted. Circuit breaker tripped.")

    def get_summary(self):
        return {**self.metrics, "current_key": self.current_key_index + 1}
