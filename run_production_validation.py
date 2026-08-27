"""
run_production_validation.py

Production Validation Script for FRIDAY Media OS.
For each brand:
1. Counts the number of successfully posted videos in Firestore scheduled_posts.
2. If less than 4, loops to generate, render, validate, upload, and verify until 4 uploads exist.
3. Uses the autonomous Google Agent client + Verification Layer.
4. Uses the production render pipeline to generate MoviePy videos.
5. Runs ffprobe verification checks to enforce YouTube compliance.
6. Uses the existing upload worker to publish private videos on YouTube.
7. Updates all Firestore records.
"""

import os
os.environ["GOOGLE_CLOUD_PROJECT"] = "friday-media-prod"
os.environ["GCP_PROJECT_ID"] = "friday-media-prod"
os.environ["GCS_BUCKET_NAME"] = "friday-media-assets-prod"

import sys
import json
import time
import datetime
import subprocess
import tempfile
from google.cloud import firestore
from src.config.brand_registry import BRAND_REGISTRY
from src.agents.google_agent_client import GoogleAgentClient
from src.verification.verification_layer import VerificationLayer
from src.pipeline_coordinator import run_pipeline
from src.workers.youtube_worker import upload_video, download_from_gcs

def run_ffprobe(filepath: str) -> dict:
    """Executes ffprobe and returns the parsed JSON output."""
    cmd = [
        "ffprobe",
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        filepath
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise ValueError(f"ffprobe failed: {res.stderr}")
    return json.loads(res.stdout)

def validate_video_file(filepath: str) -> tuple[bool, list[str]]:
    """Validates the video file against the YouTube production standard."""
    errors = []
    try:
        probe = run_ffprobe(filepath)
    except Exception as e:
        return False, [f"Could not probe video file: {e}"]

    # 1. Container check
    fmt = probe.get("format", {})
    fmt_name = fmt.get("format_name", "")
    if "mp4" not in fmt_name and "mov" not in fmt_name:
        errors.append(f"Invalid container format: {fmt_name} (must be mp4/mov)")

    # 2. Streams check
    streams = probe.get("streams", [])
    video_stream = None
    audio_stream = None
    for s in streams:
        if s.get("codec_type") == "video":
            video_stream = s
        elif s.get("codec_type") == "audio":
            audio_stream = s

    if not video_stream:
        errors.append("Missing video stream")
    else:
        # Codec
        codec = video_stream.get("codec_name", "")
        if codec != "h264":
            errors.append(f"Invalid video codec: {codec} (must be h264)")
        # Resolution (1080x1920 portrait or 1920x1080 landscape)
        width = int(video_stream.get("width", 0))
        height = int(video_stream.get("height", 0))
        if min(width, height) < 720:
            errors.append(f"Resolution too low: {width}x{height} (min 720p)")
        # Framerate
        r_frame_rate = video_stream.get("r_frame_rate", "")
        if "/" in r_frame_rate:
            num, den = map(int, r_frame_rate.split("/"))
            fps = num / den if den != 0 else 0
        else:
            fps = float(r_frame_rate) if r_frame_rate else 0
        if fps < 24.0:
            errors.append(f"Frame rate too low: {fps} fps (min 24 fps)")

    if not audio_stream:
        errors.append("Missing audio stream")
    else:
        # Codec
        acodec = audio_stream.get("codec_name", "")
        if acodec != "aac":
            errors.append(f"Invalid audio codec: {acodec} (must be aac)")
        # Channels
        channels = int(audio_stream.get("channels", 0))
        if channels < 2:
            errors.append(f"Audio channels: {channels} (must be at least stereo/2 channels)")
        # Sample rate
        sample_rate = int(audio_stream.get("sample_rate", 0))
        if sample_rate < 44100:
            errors.append(f"Audio sample rate: {sample_rate} Hz (min 44100 Hz)")

    return len(errors) == 0, errors

def perform_validation():
    db = firestore.Client(project="friday-media-prod")
    agent_client = GoogleAgentClient(project_id="friday-media-prod")
    verifier = VerificationLayer()

    print("=== STARTING PRODUCTION VALIDATION CYCLE ===")
    
    for brand_id, profile in BRAND_REGISTRY.items():
        print(f"\n--- Checking Brand: {brand_id} ---")
        
        # Count existing successful posted videos
        posts = list(
            db.collection("scheduled_posts")
            .where("brand_id", "==", brand_id)
            .where("status", "==", "posted")
            .stream()
        )
        successful_count = len(posts)
        print(f"Current successful posted count: {successful_count}")

        while successful_count < 4:
            print(f"\n[Generation Loop] Brand {brand_id} needs {4 - successful_count} more video(s). Generating video {successful_count + 1}/4...")

            # 1. Fetch memory
            mem_doc = db.collection("brand_memory").document(brand_id).get()
            memory_data = mem_doc.to_dict() if mem_doc.exists else {}

            # 2. Invoke Google Editorial Agent
            print(f"[{brand_id}] Waking Editorial Agent...")
            agent_package = agent_client.invoke_agent(
                brand_id=brand_id,
                brand_profile=profile,
                brand_memory=memory_data
            )
            topic = agent_package.get("topic")
            print(f"[{brand_id}] Agent decided topic: '{topic}'")

            # 3. Verification Layer
            print(f"[{brand_id}] Verifying decision...")
            v_res = verifier.verify_decision(agent_package, profile, memory_data)
            if not v_res.passed:
                print(f"❌ [{brand_id}] Verification rejected decision: {v_res.reason}. Retrying...")
                continue
            print(f"✓ [{brand_id}] Verification passed ({v_res.status})")

            # 4. Write records in Firestore
            content_id = f"val_{brand_id}_{datetime.datetime.now().strftime('%m%d_%H%M%S')}"
            print(f"[{brand_id}] Creating content item record `{content_id}`...")
            
            db.collection("content_items").document(content_id).set({
                "brand_id": brand_id,
                "topic": topic,
                "status": "draft",
                "source": "validation",
                "agent_name": agent_package.get("agent_name"),
                "category": agent_package.get("category"),
                "editorial_reasoning": agent_package.get("editorial_reasoning"),
                "confidence": agent_package.get("confidence"),
                "quality_score": agent_package.get("quality_score"),
                "verification_status": v_res.status,
                "similarity_score": v_res.metrics.get("effective_similarity"),
                "seo_title": agent_package.get("seo_title"),
                "caption": agent_package.get("description"),
                "hashtags": agent_package.get("hashtags", []),
                "script": agent_package.get("script_narration"),
                "scene_plan": agent_package.get("scene_plan", []),
                "created_at": firestore.SERVER_TIMESTAMP,
                "updated_at": firestore.SERVER_TIMESTAMP,
            })

            db.collection("content_queue").document(content_id).set({
                "brand_id": brand_id,
                "topic": topic,
                "status": "QUEUED",
                "source": "validation",
                "created_at": firestore.SERVER_TIMESTAMP,
                "updated_at": firestore.SERVER_TIMESTAMP,
            })

            # 5. Run the render pipeline locally
            print(f"[{brand_id}] Executing pipeline locally for {content_id}...")
            try:
                run_pipeline(brand_id, topic, content_id)
            except Exception as e:
                print(f"❌ [{brand_id}] Render pipeline failed: {e}")
                sys.exit(1)

            # 6. Retrieve rendered video URI from Firestore
            doc = db.collection("content_items").document(content_id).get()
            if not doc.exists:
                print(f"❌ [{brand_id}] Content document disappeared from Firestore.")
                sys.exit(1)
            
            info = doc.to_dict()
            video_uri = info.get("final_video_uri")
            srt_uri = info.get("srt_uri")
            title = info.get("seo_title") or topic
            description = info.get("caption") or ""
            hashtags = info.get("hashtags") or []

            if not video_uri:
                print(f"❌ [{brand_id}] final_video_uri was not found in Firestore.")
                sys.exit(1)

            # 7. Download and validate video file via ffprobe
            with tempfile.TemporaryDirectory() as tmpdir:
                local_path = os.path.join(tmpdir, f"val_{content_id}.mp4")
                print(f"[{brand_id}] Downloading rendered video from GCS: {video_uri}...")
                download_from_gcs(video_uri, local_path)
                
                print(f"[{brand_id}] Running FFprobe validation on local file...")
                passed, errors = validate_video_file(local_path)
                if not passed:
                    print(f"❌ [{brand_id}] Video failed FFprobe validation: {errors}")
                    sys.exit(1)
                print(f"✓ [{brand_id}] Video passed all FFprobe validation checks.")

            # 8. Create scheduled post record
            print(f"[{brand_id}] Creating pending post record...")
            post_ref = db.collection("scheduled_posts").document()
            post_ref.set({
                "content_id": content_id,
                "brand_id": brand_id,
                "topic": topic,
                "platform": "YouTube",
                "scheduled_time": datetime.datetime.now(datetime.UTC),
                "status": "pending",
                "created_at": firestore.SERVER_TIMESTAMP,
                "ai_title": title,
                "ai_caption": description,
                "ai_hashtags": hashtags,
                "chosen_title": title,
                "chosen_caption": description,
                "chosen_hashtags": hashtags,
            })

            # 9. Upload to YouTube via existing worker
            print(f"[{brand_id}] Uploading video to YouTube (Private)...")
            try:
                youtube_url = upload_video(
                    channel=brand_id,
                    content_id=content_id,
                    video_gs_uri=video_uri,
                    title=title,
                    description=description,
                    hashtags=hashtags,
                    srt_gs_uri=srt_uri
                )
                print(f"✓ [{brand_id}] YouTube upload completed successfully: {youtube_url}")
            except Exception as e:
                print(f"❌ [{brand_id}] YouTube upload failed: {e}")
                sys.exit(1)

            # 10. Update scheduled post and queue statuses
            print(f"[{brand_id}] Finalizing status updates in Firestore...")
            post_ref.update({
                "status": "posted",
                "youtube_url": youtube_url,
                "posted_at": firestore.SERVER_TIMESTAMP,
            })
            db.collection("content_queue").document(content_id).update({
                "status": "PUBLISHED",
                "updated_at": firestore.SERVER_TIMESTAMP
            })
            print(f"✓ [{brand_id}] Firestore statuses updated.")
            
            successful_count += 1
            print(f"✓ [{brand_id}] Video {successful_count}/4 published successfully!")
            
            # Stagger uploads slightly
            print("Staggering next run (5s delay)...")
            time.sleep(5)

    print("\n=== PRODUCTION VALIDATION COMPLETED SUCCESSFULLY ===")

if __name__ == "__main__":
    perform_validation()
