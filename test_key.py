import os
from google import genai

# Force the project environment variable to match the production project
os.environ["GOOGLE_CLOUD_PROJECT"] = "friday-media-prod"
os.environ["GCP_PROJECT_ID"] = "friday-media-prod"

key = os.environ.get("SECONDARY_KEY")
if not key:
    print("Error: SECONDARY_KEY not set")
    exit(1)

print(f"Testing key: {key[:5]}...")

try:
    # Explicitly disable Vertex AI to use direct Gemini API
    client = genai.Client(api_key=key, vertexai=False)
    for model in client.models.list():
        if 'gemini' in model.name:
            print(model.name)
except Exception as e:
    print("Error:", e)
