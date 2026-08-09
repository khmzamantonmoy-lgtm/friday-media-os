"""
tests/conftest.py
Global fixtures shared across all test tiers.
Zero production writes. Read-only Firestore access only in Tier 3.
"""
import os
import datetime
import pytest

os.environ.setdefault("GCP_PROJECT_ID", "friday-media-prod")
os.environ.setdefault("GCP_REGION", "us-central1")


@pytest.fixture
def brands():
    return ["bd_threatpulse", "wealthwise", "kids_universe", "philosophy"]


@pytest.fixture
def today_start():
    return datetime.datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)


@pytest.fixture
def today_iso():
    return datetime.datetime.utcnow().date().isoformat()


@pytest.fixture
def ro_db():
    """Live Firestore client — READ-ONLY. Only used in Tier 3."""
    try:
        from google.cloud import firestore
        return firestore.Client(project=os.environ.get("GCP_PROJECT_ID", "friday-media-prod"))
    except Exception:
        pytest.skip("Firestore not available in this environment")
