import os
from google import genai
import time

PROJECT_ID = "friday-media-prod"
LOCATION = "us-central1"
# A known stable model
MODEL_NAME = "gemini-1.5-flash"

print(f"--- PROOF OF LIFE ---")
print(f"Project: {PROJECT_ID}")
print(f"Region: {LOCATION}")

def run_test(client_config, auth_mode):
    print(f"\n--- Testing Mode: {auth_mode} ---")
    try:
        start = time.time()
        client = genai.Client(**client_config)
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents="Say Hello"
        )
        duration = time.time() - start
        print(f"✓ Success. Duration: {duration:.2f}s")
        print(f"Response: {response.text[:50]}")
    except Exception as e:
        print(f"❌ Failure. Exception: {type(e).__name__}")
        print(f"Details: {str(e)[:200]}")

# Test 1: Vertex AI (IAM)
run_test({
    "vertexai": True,
    "project": PROJECT_ID,
    "location": LOCATION
}, "Vertex AI (IAM)")

# Test 2: API Key
key = os.environ.get("SECONDARY_KEY")
if key:
    run_test({
        "api_key": key,
        "vertexai": False
    }, "API Key")
else:
    print("\n[C/D] API Key not set.")
