import os
from google import genai

# Setup environment to mimic production
os.environ["GOOGLE_CLOUD_PROJECT"] = "friday-media-prod"
os.environ["GCP_PROJECT_ID"] = "friday-media-prod"

print("--- DIAGNOSTIC: DISCOVERING AVAILABLE MODELS ---")

# 1. Test via Vertex AI (IAM)
try:
    print("\nAttempting Vertex AI Model Discovery...")
    client = genai.Client(
        vertexai=True,
        project="friday-media-prod",
        location="us-central1"
    )
    models = list(client.models.list())
    for model in models:
        if 'gemini' in model.name:
            print(f"- {model.name}")
except Exception as e:
    print(f"Vertex AI Discovery Failed: {e}")

# 2. Test via API Key (if provided)
key = os.environ.get("SECONDARY_KEY")
if key:
    try:
        print("\nAttempting API Key Model Discovery...")
        client = genai.Client(api_key=key, vertexai=False)
        models = list(client.models.list())
        for model in models:
            if 'gemini' in model.name:
                print(f"- {model.name}")
    except Exception as e:
        print(f"API Key Discovery Failed: {e}")
else:
    print("\nNo SECONDARY_KEY provided for API Key discovery test.")
