import os
from google import genai

# Setup production environment
os.environ["GOOGLE_CLOUD_PROJECT"] = "friday-media-prod"
os.environ["GCP_PROJECT_ID"] = "friday-media-prod"

PROJECT_ID = "friday-media-prod"
LOCATION = "us-central1"
# Test the newer version
MODEL = "gemini-1.5-flash-8b"

print(f"--- PROOF OF LIFE ---")
print(f"Model: {MODEL}")

try:
    client = genai.Client(vertexai=True, project=PROJECT_ID, location=LOCATION)
    response = client.models.generate_content(
        model=MODEL,
        contents="Say Hello"
    )
    print(f"✓ Success. Response: {response.text[:50]}")
except Exception as e:
    print(f"❌ Failure. Details: {str(e)[:200]}")
