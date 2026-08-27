import os
import json
import logging
import urllib.request
import urllib.parse
from google.cloud import secretmanager

logger = logging.getLogger(__name__)

PROJECT_ID = os.environ.get("GCP_PROJECT_ID", "friday-media-prod")
SECRET_ID = "meta-system-user-token"
VERSION_ID = "latest"  # Always resolves to the current validated version (v4+)

class MetaTokenInvalidError(Exception):
    """Exception raised when a Meta OAuth token is invalid or expired (OAuth Error Code 190)."""
    pass

def access_secret_version(secret_id: str, version_id: str = "latest") -> str:
    """Accesses a secret version in GCP Secret Manager."""
    client = secretmanager.SecretManagerServiceClient()
    name = f"projects/{PROJECT_ID}/secrets/{secret_id}/versions/{version_id}"
    response = client.access_secret_version(request={"name": name})
    return response.payload.data.decode("UTF-8").strip()

def _make_graph_request(url: str, params: dict = None) -> dict:
    """Helper to perform requests to Meta Graph API and parse error payloads."""
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url)
    try:
        with urllib.request.urlopen(req) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8")
        try:
            err_json = json.loads(error_body)
            error_details = err_json.get("error", {})
            error_code = error_details.get("code")
            error_subcode = error_details.get("error_subcode")
            error_type = error_details.get("type")
            error_msg = error_details.get("message", error_body)
            
            # Check for invalid / expired token (OAuthException, code 190)
            if error_code == 190 or error_type == "OAuthException":
                raise MetaTokenInvalidError(
                    f"Meta access token is invalid or expired (code={error_code}, subcode={error_subcode}): {error_msg}"
                )
            
            raise RuntimeError(f"Meta Graph API HTTP {e.code} Error (code={error_code}): {error_msg}")
        except json.JSONDecodeError:
            raise RuntimeError(f"Meta Graph API HTTP {e.code} Error: {error_body}")

def get_facebook_credentials(brand_id: str, page_id: str) -> str:
    """
    Retrieves the Page Access Token for a specific brand's Page ID dynamically.
    Fetches the parent System User Token from Secret Manager, queries /me/accounts,
    and returns the matching page-level access token.
    All credentials remain in-memory only.
    """
    if not page_id:
        raise ValueError(f"Missing facebook_page_id for brand '{brand_id}'")
        
    try:
        # Retrieve System User Token from Secret Manager (in-memory only)
        system_user_token = access_secret_version(SECRET_ID, VERSION_ID)
    except Exception as e:
        logger.error(f"Failed to retrieve secret {SECRET_ID} from Secret Manager: {e}")
        raise RuntimeError(f"Secret Manager retrieval failed for Facebook auth: {e}")
        
    # Query /me/accounts to resolve page tokens
    logger.info(f"Resolving Page Access Token for Page ID {page_id}...")
    accounts_url = "https://graph.facebook.com/v26.0/me/accounts"
    
    try:
        accounts_data = _make_graph_request(accounts_url, {
            "access_token": system_user_token,
            "limit": 100
        })
    except MetaTokenInvalidError as token_err:
        logger.error(f"System User token is invalid/revoked: {token_err}")
        raise token_err
    except Exception as api_err:
        logger.error(f"Failed to query /me/accounts: {api_err}")
        raise RuntimeError(f"Meta Graph API /me/accounts query failed: {api_err}")
        
    pages = accounts_data.get("data", [])
    for page in pages:
        if str(page.get("id")) == str(page_id):
            page_token = page.get("access_token")
            if not page_token:
                raise MetaTokenInvalidError(f"No access token returned for Page ID {page_id}")
            logger.info(f"Page Access Token resolved successfully for Page ID {page_id}")
            return page_token
            
    # Page not found or system user lacks permissions on the page
    raise MetaTokenInvalidError(
        f"Page ID {page_id} was not found in the resolved accounts of the System User. "
        "Ensure the page is assigned to the System User under the Business Portfolio."
    )
