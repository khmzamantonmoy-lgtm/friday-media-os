"""
voice_worker.py

Synthesizes narration into an MP3 using Google Cloud Text-to-Speech
(Neural2 / Journey voices per brand), uploads to GCS.
"""

import os
from google.auth import default
from google.cloud import texttospeech
from google.cloud import storage

try:
    _, PROJECT_ID = default()
except Exception:
    PROJECT_ID = os.environ.get("GCP_PROJECT_ID", "friday-media-os")

BUCKET_NAME = os.environ.get("GCS_BUCKET_NAME", "friday-media-assets-prod")


def synthesize_voice(narration: str, brand_id: str, voice_id: str, content_id: str) -> str:
    """
    Returns the gs:// URI of the uploaded MP3.
    """
    tts_client = texttospeech.TextToSpeechClient()

    synthesis_input = texttospeech.SynthesisInput(text=narration)

    # Journey voices require language_code inferred from the voice name prefix (en-US-...)
    language_code = "-".join(voice_id.split("-")[:2])  # e.g. "en-US"

    voice = texttospeech.VoiceSelectionParams(
        language_code=language_code,
        name=voice_id,
    )

    audio_config = texttospeech.AudioConfig(
        audio_encoding=texttospeech.AudioEncoding.MP3,
    )

    import time
    max_retries = 3
    response = None
    for attempt in range(max_retries):
        try:
            response = tts_client.synthesize_speech(
                input=synthesis_input,
                voice=voice,
                audio_config=audio_config,
            )
            break
        except Exception as e:
            if "429" in str(e) or "ResourceExhausted" in str(e):
                time.sleep((2 ** attempt) * 2)
            else:
                raise e
    
    if response is None:
        raise RuntimeError("Failed to synthesize voice after retries.")

    storage_client = storage.Client()
    bucket = storage_client.bucket(BUCKET_NAME)
    blob_path = f"{brand_id}/audio/{content_id}.mp3"
    blob = bucket.blob(blob_path)
    blob.upload_from_string(response.audio_content, content_type="audio/mpeg")

    return f"gs://{BUCKET_NAME}/{blob_path}"
