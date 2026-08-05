import os
from google import genai

# Explicitly set project
os.environ["GOOGLE_CLOUD_PROJECT"] = "friday-media-prod"
os.environ["GCP_PROJECT_ID"] = "friday-media-prod"

PROJECT_ID = "friday-media-prod"
LOCATION = "us-central1"
MODEL = "gemini-1.5-flash"

print(f"--- PROOF OF LIFE ---")
print(f"Project ENV: {os.environ.get('GOOGLE_CLOUD_PROJECT')}")

# Vertex AI Mode
try:
    client = genai.Client(vertexai=True, project=PROJECT_ID, location=LOCATION)
    response = client.models.generate_content(model=MODEL, contents="Hello")
    print(f"Vertex AI Mode: SUCCESS")
except Exception as e:
    print(f"Vertex AI Mode: FAILURE - {e}")

# Developer API Mode
key = os.environ.get("SECONDARY_KEY")
if key:
    try:
        client = genai.Client(api_key=key, vertexai=False)
        response = client.models.generate_content(model=MODEL, contents="Hello")
        print(f"Developer API Mode: SUCCESS")
    except Exception as e:
        print(f"Developer API Mode: FAILURE - {e}")
