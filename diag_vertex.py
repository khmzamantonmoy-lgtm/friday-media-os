import os
import json
from google import genai
from google.genai import types

# FORCE PRODUCTION CONTEXT
PROJECT_ID = "friday-media-prod"
LOCATION = "us-central1"
MODEL_NAME = "gemini-1.5-flash"

print(f"--- VERTEX AI DIAGNOSTIC ---")
print(f"Target Project: {PROJECT_ID}")
print(f"Target Location: {LOCATION}")
print(f"Target Model: {MODEL_NAME}")

try:
    # 1. Test Client Initialization
    client = genai.Client(
        vertexai=True,
        project=PROJECT_ID,
        location=LOCATION
    )
    print("✓ Client initialized.")

    # 2. Test Model Access (Simple generate)
    print("Testing generate_content...")
    response = client.models.generate_content(
        model=MODEL_NAME,
        contents="System check. Reply with 'READY'."
    )
    print(f"✓ Response received: {response.text.strip()}")
    
except Exception as e:
    print(f"❌ FAILURE: {str(e)}")
    if "403" in str(e):
        print("Root Cause: IAM Permission Denied or API Disabled.")
    elif "404" in str(e):
        print("Root Cause: Model not found in this region/version.")
