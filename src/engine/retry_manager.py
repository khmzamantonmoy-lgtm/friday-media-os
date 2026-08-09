import time
import random
import logging
from typing import Callable, Any
from google.cloud import firestore

logger = logging.getLogger(__name__)

def with_retry(max_retries: int = 5, base_delay: float = 1.0):
    """
    Decorator to wrap any callable with retry logic.
    Exponential backoff: base_delay * (2 ** attempt) + random jitter(0-2s)
    """
    def decorator(func: Callable):
        def wrapper(*args, **kwargs):
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    error_msg = str(e).lower()
                    if "429" in error_msg:
                        delay = max(60.0, base_delay * (2 ** attempt) + random.uniform(0, 2))
                    elif "503" in error_msg:
                        delay = max(30.0, base_delay * (2 ** attempt) + random.uniform(0, 2))
                    else:
                        delay = base_delay * (2 ** attempt) + random.uniform(0, 2)
                    
                    if attempt == max_retries - 1:
                        logger.error(f"Max retries reached for {func.__name__}. Writing to dead-letter queue.")
                        # write to dead letter queue
                        try:
                            db = firestore.Client()
                            db.collection("dead_letter_queue").add({
                                "function": func.__name__,
                                "args": str(args),
                                "kwargs": str(kwargs),
                                "error": str(e),
                                "timestamp": firestore.SERVER_TIMESTAMP
                            })
                        except Exception as dlq_e:
                            logger.error(f"Failed to write to dead-letter queue: {dlq_e}")
                        raise e
                    
                    logger.warning(f"Error in {func.__name__}: {e}. Retrying in {delay:.2f}s (Attempt {attempt + 1}/{max_retries})")
                    time.sleep(delay)
        return wrapper
    return decorator
