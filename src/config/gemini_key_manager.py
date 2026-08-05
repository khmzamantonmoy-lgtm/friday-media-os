"""
gemini_key_manager.py

Production-grade Gemini API Key Manager with multi-key failover and rotation.
Sourced from environment variables or Secret Manager.
"""

import os
import time
import logging
import json
from google import genai
from google.genai import types

logger = logging.getLogger("gemini_key_manager")

class GeminiKeyManager:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(GeminiKeyManager, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        
        self.keys = self._load_keys()
        self.current_key_index = 0
        self.metrics = {
            "failover_count": 0,
            "quota_failures": 0,
            "successful_recoveries": 0
        }
        self._initialized = True
        
        if not self.keys:
            logger.warning("No Gemini API keys found. System will fall back to Vertex AI (IAM).")

    def _load_keys(self):
        """Loads API keys from environment variables or Secret Manager."""
        keys = []
        
        # 1. Check GEMINI_API_KEYS (comma separated)
        env_keys = os.environ.get("GEMINI_API_KEYS")
        if env_keys:
            keys.extend([k.strip() for k in env_keys.split(",") if k.strip()])
        
        # 2. Check individual variables
        for var in ["PRIMARY_KEY", "SECONDARY_KEY", "TERTIARY_KEY"]:
            val = os.environ.get(var)
            if val:
                keys.append(val)
        
        # 3. deduplicate while preserving order
        seen = set()
        return [k for k in keys if not (k in seen or seen.add(k))]

    def get_client(self):
        """Returns a genai.Client using the active key, or Vertex AI if no keys exist."""
        if not self.keys:
            # Fallback to Vertex AI (IAM)
            return genai.Client(
                vertexai=True,
                project=os.environ.get("GCP_PROJECT_ID", "friday-media-prod"),
                location=os.environ.get("GCP_REGION", "us-central1")
            )
        
        return genai.Client(api_key=self.keys[self.current_key_index])

    def rotate_key(self):
        """Rotates to the next available API key."""
        if not self.keys or len(self.keys) <= 1:
            return False
        
        self.current_key_index = (self.current_key_index + 1) % len(self.keys)
        self.metrics["failover_count"] += 1
        logger.info(f"Rotating to Gemini API Key #{self.current_key_index + 1}")
        return True

    def execute_with_failover(self, operation_fn):
        """
        Executes a Gemini API operation with exponential backoff and key rotation.
        operation_fn: A lambda or function that takes a genai.Client and returns a response.
        """
        max_retries_per_key = 3
        
        # We try each key until success or all keys exhausted
        keys_tried = 0
        total_keys = len(self.keys)
        
        # Phase 1: Try all dedicated API keys
        while keys_tried < total_keys:
            client = genai.Client(api_key=self.keys[self.current_key_index])
            key_label = f"Key #{self.current_key_index + 1}"
            
            for attempt in range(max_retries_per_key):
                try:
                    response = operation_fn(client)
                    if keys_tried > 0 or attempt > 0:
                        self.metrics["successful_recoveries"] += 1
                    return response
                except Exception as e:
                    err_msg = str(e).upper()
                    if "429" in err_msg or "RESOURCE_EXHAUSTED" in err_msg:
                        self.metrics["quota_failures"] += 1
                        wait_time = (2 ** attempt) * 5
                        logger.warning(f"[{key_label}] Quota exhausted (429). Retry {attempt+1}/{max_retries_per_key} in {wait_time}s...")
                        time.sleep(wait_time)
                    else:
                        raise e
            
            self.rotate_key()
            keys_tried += 1
            logger.warning(f"Retries exhausted for {key_label}. Failing over...")

        # Phase 2: Final fallback to Vertex AI (IAM)
        logger.warning("All API keys exhausted. Attempting final fallback to Vertex AI (IAM)...")
        vertex_client = genai.Client(
            vertexai=True,
            project=os.environ.get("GCP_PROJECT_ID", "friday-media-prod"),
            location=os.environ.get("GCP_REGION", "us-central1")
        )
        try:
            return operation_fn(vertex_client)
        except Exception as e:
            logger.error(f"Final Vertex AI fallback failed: {e}")
            raise RuntimeError(f"Gemini API failover exhausted. All {total_keys} keys and Vertex AI returned errors.")

    def get_summary(self):
        """Returns a summary of metrics."""
        return {
            "active_key_index": self.current_key_index,
            "total_keys": len(self.keys),
            **self.metrics
        }
