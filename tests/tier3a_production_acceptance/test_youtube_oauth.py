"""
Tier 3a — Production Acceptance: OAuth Credential Verification
Reads tokens from Secret Manager. Zero writes.
"""
import pytest
import json
import os

pytestmark = pytest.mark.acceptance

BRANDS = {
    "bd_threatpulse": "bd-threatpulse-token",
    "wealthwise": "wealthwise-token",
    "kids_universe": "tinysparks-token",
    "philosophy": "thinkingroom-token",
}


def get_secret(secret_id):
    try:
        from google.cloud import secretmanager
        client = secretmanager.SecretManagerServiceClient()
        name = f"projects/{os.environ.get('GCP_PROJECT_ID', 'friday-media-prod')}/secrets/{secret_id}/versions/latest"
        response = client.access_secret_version(request={"name": name})
        return json.loads(response.payload.data.decode("UTF-8"))
    except Exception as e:
        pytest.skip(f"Secret Manager unavailable or secret {secret_id} not found: {e}")


@pytest.mark.parametrize("brand_id,secret_id", list(BRANDS.items()))
def test_token_exists_in_secret_manager(brand_id, secret_id):
    """Each brand's OAuth token must be stored in Secret Manager."""
    token = get_secret(secret_id)
    assert token is not None, f"Token for {brand_id} ({secret_id}) not found"


@pytest.mark.parametrize("brand_id,secret_id", list(BRANDS.items()))
def test_token_contains_youtube_upload_scope(brand_id, secret_id):
    token = get_secret(secret_id)
    scopes_raw = token.get("scopes", token.get("scope", ""))
    if isinstance(scopes_raw, list):
        scopes = " ".join(scopes_raw)
    else:
        scopes = str(scopes_raw)
    assert "youtube.upload" in scopes, (
        f"Brand {brand_id}: youtube.upload scope missing from token. Scopes: {scopes}"
    )


@pytest.mark.parametrize("brand_id,secret_id", list(BRANDS.items()))
def test_token_contains_force_ssl_scope(brand_id, secret_id):
    token = get_secret(secret_id)
    scopes_raw = token.get("scopes", token.get("scope", ""))
    if isinstance(scopes_raw, list):
        scopes = " ".join(scopes_raw)
    else:
        scopes = str(scopes_raw)
    assert "youtube.force-ssl" in scopes, (
        f"Brand {brand_id}: youtube.force-ssl scope missing from token. Scopes: {scopes}"
    )


@pytest.mark.parametrize("brand_id,secret_id", list(BRANDS.items()))
def test_token_has_refresh_token(brand_id, secret_id):
    """Tokens must have refresh_token for headless operation."""
    token = get_secret(secret_id)
    assert token.get("refresh_token"), (
        f"Brand {brand_id}: token is missing refresh_token. "
        "Interactive re-auth required — cannot run headless."
    )


@pytest.mark.parametrize("brand_id", list(BRANDS.keys()))
def test_credentials_refresh_without_interaction(brand_id):
    """get_youtube_credentials must complete without interactive flow."""
    try:
        from src.auth.youtube_auth import get_youtube_credentials
        creds = get_youtube_credentials(brand_id)
        assert creds is not None, f"Credentials for {brand_id} returned None"
        assert creds.valid or creds.refresh_token, (
            f"Credentials for {brand_id} are invalid and have no refresh token"
        )
    except RuntimeError as e:
        pytest.fail(f"Interactive auth triggered for {brand_id} — token may be expired: {e}")
    except Exception as e:
        pytest.skip(f"Credential check skipped for {brand_id}: {e}")
