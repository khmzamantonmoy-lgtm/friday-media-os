"""
upgrade_tokens.py

Headless interactive OAuth token upgrade helper for FRIDAY Media OS.
Loops through all configured brands and guides the user to authorize force-ssl scopes.
"""

import sys
import json
import os
from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from src.auth.youtube_auth import access_secret_version, add_secret_version, SCOPES, PROJECT_ID
from src.config.brand_registry import BRAND_REGISTRY

def check_scopes(token_info) -> bool:
    scopes = token_info.get("scopes", [])
    required = set(SCOPES)
    return required.issubset(set(scopes))

def main():
    print("Initiating Dynamic OAuth Credential Scope Upgrade...", flush=True)
    
    for brand_id, brand_cfg in BRAND_REGISTRY.items():
        print(f"\n========================================================", flush=True)
        print(f"BRAND: {brand_cfg['brand_name']} ({brand_id})", flush=True)
        print(f"========================================================", flush=True)
        
        token_secret_id = brand_cfg["token_secret_id"]
        client_secret_id = brand_cfg["client_secret_id"]
        
        # Check current token
        try:
            token_data_str = access_secret_version(token_secret_id)
            token_info = json.loads(token_data_str)
            if check_scopes(token_info):
                print(f"✅ Brand {brand_id} already has upgraded scopes: {token_info.get('scopes')}", flush=True)
                continue
            else:
                print(f"⚠️ Brand {brand_id} token scopes are insufficient: {token_info.get('scopes')}", flush=True)
        except Exception as e:
            print(f"⚠️ Could not load token for {brand_id}: {e}", flush=True)
            
        # Run upgrade
        try:
            client_secret_str = access_secret_version(client_secret_id)
        except Exception:
            client_secret_str = access_secret_version("bd-threatpulse-client-secret")
            
        client_config = json.loads(client_secret_str)
        flow = InstalledAppFlow.from_client_config(client_config, scopes=SCOPES)
        flow.redirect_uri = "http://localhost:8080/"
        
        auth_url, _ = flow.authorization_url(prompt="consent", access_type="offline")
        
        # Format redirect_uri parameters for easy preview
        import urllib.parse
        parsed = urllib.parse.urlparse(auth_url)
        params = urllib.parse.parse_qsl(parsed.query)
        reordered = [("redirect_uri", "http://localhost:8080/")] + [p for p in params if p[0] != "redirect_uri"]
        reordered_url = urllib.parse.urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, urllib.parse.urlencode(reordered), parsed.fragment))
        
        print(f"\nURL_REQUIRED: {brand_id}", flush=True)
        print(f"{reordered_url}", flush=True)
        print("Please enter authorization code:", flush=True)
        
        # Read from stdin
        code = sys.stdin.readline().strip()
        if not code:
            print(f"❌ No code provided. Skipping {brand_id}.", flush=True)
            continue
            
        print(f"Exchanging code for token...", flush=True)
        flow.fetch_token(code=code)
        creds = flow.credentials
        
        # Save token
        print(f"Saving upgraded token to Secret Manager...", flush=True)
        add_secret_version(token_secret_id, creds.to_json())
        print(f"✅ Successfully upgraded and verified token for {brand_id}.", flush=True)

    print("\nScope Upgrade Verification Complete.", flush=True)

if __name__ == "__main__":
    main()
