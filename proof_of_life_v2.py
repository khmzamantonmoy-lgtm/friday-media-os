import os
from google import genai

# Setup production environment
os.environ["GOOGLE_CLOUD_PROJECT"] = "friday-media-prod"
os.environ["GCP_PROJECT_ID"] = "friday-media-prod"

PROJECT_ID = "friday-media-prod"
LOCATION = "us-central1"

print(f"--- PROOF OF LIFE ---")
print(f"Project: {PROJECT_ID}")
print(f"Region: {LOCATION}")

def test_model(model_name):
    print(f"\n--- Testing Model: {model_name} ---")
    try:
        # Vertex AI client
        client = genai.Client(vertexai=True, project=PROJECT_ID, location=LOCATION)
        response = client.models.generate_content(
            model=model_name,
            contents="Say Hello"
        )
        print(f"✓ Success. Response: {response.text[:50]}")
    except Exception as e:
        print(f"❌ Failure. Details: {str(e)[:200]}")

# Phase 4: Test Candidates
candidates = ["gemini-1.5-flash", "gemini-1.5-flash-002", "gemini-1.5-pro-002", "gemini-2.0-flash"]
for model in candidates:
    test_model(model)
