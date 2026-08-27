"""
youtube_auth.py

Multi-Channel Dynamic YouTube OAuth Authentication & Token Management for FRIDAY Media OS.
Reads configuration from centralized brand_registry.py and resolves client secrets and tokens
from GCP Secret Manager.
"""

import os
import json
import sys
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from google.cloud import secretmanager
from src.config.brand_registry import BRAND_REGISTRY, get_brand_config

PROJECT_ID = os.environ.get("GCP_PROJECT_ID", "friday-media-prod")
SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.force-ssl"
]


def access_secret_version(secret_id: str, version_id: str = "latest") -> str:
    """Accesses a secret version in GCP Secret Manager."""
    client = secretmanager.SecretManagerServiceClient()
    name = f"projects/{PROJECT_ID}/secrets/{secret_id}/versions/{version_id}"
    response = client.access_secret_version(request={"name": name})
    return response.payload.data.decode("UTF-8")


def add_secret_version(secret_id: str, payload_data: str) -> str:
    """Adds a new secret version to Secret Manager."""
    client = secretmanager.SecretManagerServiceClient()
    parent = f"projects/{PROJECT_ID}/secrets/{secret_id}"
    payload = payload_data.encode("UTF-8")
    response = client.add_secret_version(
        request={"parent": parent, "payload": {"data": payload}}
    )
    return response.name


def get_youtube_credentials(channel: str, force_reauth: bool = False):
    """
    Retrieves authorized YouTube API credentials for the requested channel.
    Resolves client secrets and tokens dynamically via Secret Manager.
    """
    brand_cfg = get_brand_config(channel)
    client_secret_id = brand_cfg["client_secret_id"]
    token_secret_id = brand_cfg["token_secret_id"]

    creds = None

    # 1. Attempt to load token from Secret Manager
    if not force_reauth:
        try:
            token_data_str = access_secret_version(token_secret_id)
            token_info = json.loads(token_data_str)
            scopes = token_info.get("scopes", SCOPES)
            creds = Credentials.from_authorized_user_info(token_info, scopes)
            print(f"Loaded token from Secret Manager for channel '{channel}' ({brand_cfg['youtube_channel_name']})")
        except Exception as e:
            print(f"No token in Secret Manager for {channel} ({token_secret_id}): {e}")
            # No token found; will proceed to interactive authentication flow.


    # 2. Refresh credentials if expired
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                try:
                    add_secret_version(token_secret_id, creds.to_json())
                    print(f"Successfully refreshed and updated token for {channel} in Secret Manager.")
                except Exception as save_err:
                    print(f"Refreshed token in-memory (Secret Manager update skipped: {save_err})")
            except Exception as e:
                print(f"Error refreshing token for {channel}: {e}")
                creds = None

        if not creds:
            # 3. Interactive fallback consent flow
            try:
                client_secret_str = access_secret_version(client_secret_id)
            except Exception:
                client_secret_str = access_secret_version("bd-threatpulse-client-secret")
            
            client_config = json.loads(client_secret_str)
            flow = InstalledAppFlow.from_client_config(client_config, scopes=SCOPES)
            flow.redirect_uri = "http://localhost:8080/"
            auth_url, _ = flow.authorization_url(prompt="consent", access_type="offline")

            import urllib.parse
            parsed = urllib.parse.urlparse(auth_url)
            params = urllib.parse.parse_qsl(parsed.query)
            reordered = [("redirect_uri", "http://localhost:8080/")] + [p for p in params if p[0] != "redirect_uri"]
            reordered_url = urllib.parse.urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, urllib.parse.urlencode(reordered), parsed.fragment))

            print("\n" + "=" * 80)
            print(f"YOUTUBE AUTHENTICATION REQUIRED FOR BRAND: {brand_cfg['brand_name'].upper()}")
            print("Please open the following authorization link:")
            print(reordered_url)
            print("=" * 80 + "\n")

            # Determine authorization code
            import os
            env_code = os.getenv("YOUTUBE_AUTH_CODE")
            if env_code:
                code = env_code
                print("Using authorization code from environment variable YOUTUBE_AUTH_CODE")
            elif len(sys.argv) > 2:
                code = sys.argv[2]
                print("Using authorization code from command‑line argument")
            else:
                # RAISE ERROR instead of input() for production safety
                raise RuntimeError(
                    f"YouTube token for {channel} is invalid and no authorization code was provided. "
                    "Run youtube_auth.py locally to generate a new token."
                )

            flow.fetch_token(code=code)
            creds = flow.credentials
            try:
                add_secret_version(token_secret_id, creds.to_json())
                print(f"Saved new token for {channel} to Secret Manager.")
            except Exception as save_err:
                print(f"Token active in-memory ({save_err})")

    return creds


if __name__ == "__main__":
    channel_arg = "bd_threatpulse"
    if len(sys.argv) > 1:
        channel_arg = sys.argv[1]
    get_youtube_credentials(channel_arg, force_reauth=True)
