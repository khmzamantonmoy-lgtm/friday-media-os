import os
from google import genai
from google.genai import types

# FORCE PRODUCTION CONTEXT
os.environ["GOOGLE_CLOUD_PROJECT"] = "friday-media-prod"
os.environ["GCP_PROJECT_ID"] = "friday-media-prod"

PROJECT_ID = "friday-media-prod"
LOCATION = "us-central1"
MODEL_NAME = "gemini-1.5-flash"

print(f"--- LIVE CONNECTIVITY TEST ---")
print(f"Project: {os.environ.get('GOOGLE_CLOUD_PROJECT')}")

# A/B: Vertex AI (IAM)
try:
    print("\n[A/B] Testing Vertex AI (IAM)...")
    client = genai.Client(vertexai=True, project=PROJECT_ID, location=LOCATION)
    response = client.models.generate_content(
        model=MODEL_NAME,
        contents="Say Hello (Vertex)"
    )
    print("✓ Success (Vertex):", response.text[:20])
except Exception as e:
    print(f"❌ Failure (Vertex): {str(e)[:100]}")

# C/D: API Key
key = os.environ.get("SECONDARY_KEY")
if key:
    try:
        print("\n[C/D] Testing API Key...")
        client = genai.Client(api_key=key, vertexai=False)
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents="Say Hello (Key)"
        )
        print("✓ Success (Key):", response.text[:20])
        print("Models found:", [m.name for m in client.models.list() if 'gemini' in m.name][:3])
    except Exception as e:
        print(f"❌ Failure (Key): {str(e)[:100]}")
else:
    print("\n[C/D] API Key not set.")
