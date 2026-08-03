import os
import json
import datetime
import logging
import pytz
from google.cloud import firestore
from src.job_trigger import trigger_pipeline_job
from src.workers.youtube_worker import upload_video

logger = logging.getLogger("autonomous_scheduler")
logging.basicConfig(level=logging.INFO)


def calculate_next_available_slot(
    db, brand_id: str, publish_windows: list, timezone_str: str
) -> datetime.datetime:
    """Finds the next empty publication window slot using indexed query."""
    try:
        tz = pytz.timezone(timezone_str)
    except Exception:
        tz = pytz.UTC

    now = datetime.datetime.now(tz)

    for day_offset in range(7):
        target_date = now + datetime.timedelta(days=day_offset)
        for window in publish_windows:
            try:
                start_str, end_str = window.split("-")
                sh, sm = map(int, start_str.strip().split(":"))
                eh, em = map(int, end_str.strip().split(":"))
                slot_start = target_date.replace(
                    hour=sh, minute=sm, second=0, microsecond=0
                )
                slot_end = target_date.replace(
                    hour=eh, minute=em, second=0, microsecond=0
                )
            except Exception as e:
                logger.warning(f"Failed to parse window '{window}': {e}")
                continue

            if slot_end < now:
                continue

            # Use indexed composite query: brand_id ASC, scheduled_time ASC
            conflicts = list(
                db.collection("scheduled_posts")
                .where(filter=firestore.FieldFilter("brand_id", "==", brand_id))
                .where(
                    filter=firestore.FieldFilter(
                        "scheduled_time", ">=", slot_start
                    )
                )
                .where(
                    filter=firestore.FieldFilter(
                        "scheduled_time", "<=", slot_end
                    )
                )
                .limit(1)
                .stream()
            )

            if not conflicts:
                import random

                duration_minutes = int(
                    (slot_end - slot_start).total_seconds() / 60
                )
                random_offset = random.randint(0, max(0, duration_minutes))
                return slot_start + datetime.timedelta(minutes=random_offset)

    # Fallback: 2 hours from now
    return datetime.datetime.now(pytz.UTC) + datetime.timedelta(hours=2)


def generate_ai_topic(db, brand_id: str, brand_profile: dict) -> str:
    """Generates a non-repetitive topic using Gemini 2.5 Flash and brand memory."""
    mem_doc = db.collection("brand_memory").document(brand_id).get()
    recent_topics = []
    if mem_doc.exists:
        recent_topics = mem_doc.to_dict().get("recent_topics", [])

    from google import genai
    from google.genai import types

    client = genai.Client(
        vertexai=True,
        project=os.environ.get("GCP_PROJECT_ID", "friday-media-prod"),
        location=os.environ.get("GCP_REGION", "us-central1"),
    )

    prompt = (
        f"You are an expert AI content strategist. Generate a single highly engaging, "
        f"unique video topic for the brand: {brand_profile.get('display_name', brand_id)}.\n"
        f"Brand Profile:\n"
        f"- Tone: {brand_profile.get('tone', '')}\n"
        f"- Target Audience: {brand_profile.get('audience', '')}\n"
        f"- Core Angle: {brand_profile.get('content_angle', '')}\n"
        f"- Categories: {brand_profile.get('categories', [])}\n"
        f"- Target Keywords: {brand_profile.get('preferred_keywords', [])}\n"
        f"- Avoid: {brand_profile.get('avoid_topics', [])}\n\n"
        f"To prevent repetition, do NOT generate any topics similar to these recent topics:\n"
        f"{json.dumps(recent_topics)}\n\n"
        f"Output ONLY the topic string (max 80 chars), no description, no quotes, no formatting."
    )

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=types.GenerateContentConfig(temperature=0.7),
    )
    return response.text.strip().strip('"').strip("'")


def run_scheduler() -> dict:
    """
    Orchestrates one autonomous cycle:
    1. Scan READY content queue items → schedule them.
    2. Check brand daily quotas → trigger new pipeline runs (Calendar / AI / Hybrid).
    3. Auto-publish due pending posts.
    """
    logger.info("Starting autonomous scheduler execution...")
    db = firestore.Client()

    settings_doc = db.collection("automation_settings").document("global").get()
    if not settings_doc.exists:
        logger.warning("No global automation settings found.")
        return {"status": "skipped", "reason": "No automation settings"}

    settings = settings_doc.to_dict()
    if not settings.get("enabled", False):
        logger.info("Automation is disabled globally.")
        return {"status": "skipped", "reason": "Automation disabled"}

    timezone_str = settings.get("timezone", "UTC")
    publish_windows = settings.get(
        "publish_windows", ["09:00-11:00", "13:00-15:00", "18:00-21:00"]
    )

    results = {"scheduled": [], "triggered": [], "published": [], "errors": []}

    # ── STEP 1: READY items → schedule them ──────────────────────────────────
    ready_items = list(
        db.collection("content_queue")
        .where(filter=firestore.FieldFilter("status", "==", "READY"))
        .stream()
    )
    for doc in ready_items:
        try:
            item = doc.to_dict()
            content_id = doc.id
            brand_id = item["brand_id"]

            content_doc = db.collection("content_items").document(content_id).get()
            if not content_doc.exists:
                continue

            c_data = content_doc.to_dict()
            titles = c_data.get("title_suggestions", [])
            title = titles[0] if titles else item.get("topic", "Video Post")
            caption = c_data.get("caption", "")
            hashtags = c_data.get("hashtags", [])

            slot_time = calculate_next_available_slot(
                db, brand_id, publish_windows, timezone_str
            )

            post_ref = db.collection("scheduled_posts").document()
            post_ref.set(
                {
                    "content_id": content_id,
                    "brand_id": brand_id,
                    "topic": item["topic"],
                    "platform": "YouTube",
                    "scheduled_time": slot_time,
                    "status": "pending",
                    "created_at": firestore.SERVER_TIMESTAMP,
                    "ai_title": title,
                    "ai_caption": caption,
                    "ai_hashtags": hashtags,
                    "chosen_title": title,
                    "chosen_caption": caption,
                    "chosen_hashtags": hashtags,
                }
            )

            db.collection("content_queue").document(content_id).update(
                {"status": "SCHEDULED", "updated_at": firestore.SERVER_TIMESTAMP}
            )

            results["scheduled"].append(content_id)
            logger.info(
                f"Scheduled content {content_id} for brand {brand_id} at {slot_time}"
            )
        except Exception as e:
            logger.exception(f"Failed to schedule item {doc.id}")
            results["errors"].append(f"Scheduling error: {e}")

    # ── STEP 2: Trigger new generation runs if quota permits ──────────────────
    try:
        tz = pytz.timezone(timezone_str)
    except Exception:
        tz = pytz.UTC

    now = datetime.datetime.now(tz)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start + datetime.timedelta(days=1)

    brands = list(db.collection("brand_profiles").stream())
    for brand_doc in brands:
        try:
            profile = brand_doc.to_dict()
            brand_id = brand_doc.id
            strategy = profile.get("topic_strategy", "hybrid")
            freq = profile.get("publish_frequency_per_day", 1)

            # Count today's scheduled posts using composite index (brand_id, scheduled_time)
            existing_today = list(
                db.collection("scheduled_posts")
                .where(filter=firestore.FieldFilter("brand_id", "==", brand_id))
                .where(
                    filter=firestore.FieldFilter(
                        "scheduled_time", ">=", today_start
                    )
                )
                .where(
                    filter=firestore.FieldFilter("scheduled_time", "<", today_end)
                )
                .stream()
            )

            # Count actively in-progress items using composite index (brand_id, status)
            in_progress_statuses = [
                "QUEUED",
                "GENERATING",
                "SCRIPT_READY",
                "METADATA_READY",
                "VOICE_READY",
                "IMAGES_READY",
                "RENDERING",
            ]
            active_queue = []
            for s in in_progress_statuses:
                active_queue.extend(
                    list(
                        db.collection("content_queue")
                        .where(
                            filter=firestore.FieldFilter("brand_id", "==", brand_id)
                        )
                        .where(filter=firestore.FieldFilter("status", "==", s))
                        .stream()
                    )
                )

            remaining_slots = freq - len(existing_today) - len(active_queue)
            if remaining_slots <= 0:
                logger.info(
                    f"Brand {brand_id}: no remaining slots today (existing={len(existing_today)}, active={len(active_queue)})."
                )
                continue

            logger.info(
                f"Brand {brand_id} has {remaining_slots} open slot(s) today. Triggering generation..."
            )

            # A. Editorial Calendar — indexed (brand ASC, processed ASC, date ASC)
            topic = None
            source = "ai"
            if strategy in ["calendar", "hybrid"]:
                calendar_items = list(
                    db.collection("editorial_calendar")
                    .where(filter=firestore.FieldFilter("brand", "==", brand_id))
                    .where(
                        filter=firestore.FieldFilter("processed", "==", False)
                    )
                    .order_by("date", direction=firestore.Query.ASCENDING)
                    .limit(1)
                    .stream()
                )
                if calendar_items:
                    cal_doc = calendar_items[0]
                    topic = cal_doc.to_dict().get("topic")
                    source = "calendar"
                    db.collection("editorial_calendar").document(
                        cal_doc.id
                    ).update(
                        {
                            "processed": True,
                            "status": "processed",
                            "updated_at": firestore.SERVER_TIMESTAMP,
                        }
                    )
                    logger.info(f"Retrieved topic from calendar: '{topic}'")

            # B. AI fallback
            if not topic:
                if strategy == "calendar":
                    logger.info(
                        "Calendar-only mode and calendar is empty. Skipping."
                    )
                    continue
                topic = generate_ai_topic(db, brand_id, profile)
                source = "ai"
                logger.info(f"Generated AI topic: '{topic}'")

            content_id = f"auto_{brand_id}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"

            db.collection("content_items").document(content_id).set(
                {
                    "brand_id": brand_id,
                    "topic": topic,
                    "status": "draft",
                    "source": source,
                    "created_at": firestore.SERVER_TIMESTAMP,
                    "updated_at": firestore.SERVER_TIMESTAMP,
                }
            )
            db.collection("content_queue").document(content_id).set(
                {
                    "brand_id": brand_id,
                    "topic": topic,
                    "status": "QUEUED",
                    "source": source,
                    "created_at": firestore.SERVER_TIMESTAMP,
                    "updated_at": firestore.SERVER_TIMESTAMP,
                }
            )

            trigger_pipeline_job(brand_id, topic, content_id)
            results["triggered"].append(content_id)
            logger.info(
                f"Triggered pipeline run for {content_id} (topic: {topic})"
            )

        except Exception as e:
            logger.exception(f"Failed to process brand {brand_doc.id}")
            results["errors"].append(f"Brand generation error: {e}")

    # ── STEP 3: Auto-publish due posts ────────────────────────────────────────
    now_utc = datetime.datetime.now(pytz.UTC)
    # Use indexed query: status ASC, scheduled_time ASC
    due_posts = list(
        db.collection("scheduled_posts")
        .where(filter=firestore.FieldFilter("status", "==", "pending"))
        .where(
            filter=firestore.FieldFilter("scheduled_time", "<=", now_utc)
        )
        .stream()
    )

    for doc in due_posts:
        try:
            item = doc.to_dict()
            post_id = doc.id
            content_id = item["content_id"]
            brand_id = item["brand_id"]

            content_doc = db.collection("content_items").document(content_id).get()
            if not content_doc.exists:
                continue

            c_data = content_doc.to_dict()
            video_uri = c_data.get("final_video_uri")
            srt_uri = c_data.get("srt_uri")

            title = item.get("chosen_title") or item.get("ai_title")
            description = item.get("chosen_caption") or item.get("ai_caption")
            hashtags = item.get("chosen_hashtags") or item.get("ai_hashtags", [])

            logger.info(
                f"Auto-publishing post {post_id} (content: {content_id}) to YouTube..."
            )
            youtube_url = upload_video(
                channel=brand_id,
                content_id=content_id,
                video_gs_uri=video_uri,
                title=title,
                description=description,
                hashtags=hashtags,
                srt_gs_uri=srt_uri,
            )

            db.collection("scheduled_posts").document(post_id).update(
                {
                    "status": "posted",
                    "youtube_url": youtube_url,
                    "posted_at": firestore.SERVER_TIMESTAMP,
                }
            )
            db.collection("content_queue").document(content_id).update(
                {"status": "PUBLISHED", "updated_at": firestore.SERVER_TIMESTAMP}
            )

            results["published"].append(content_id)
            logger.info(
                f"Auto-published post {post_id} → {youtube_url}"
            )
        except Exception as e:
            logger.exception(f"Failed to auto-publish post {doc.id}")
            results["errors"].append(f"Auto-publish error: {e}")

    return results


if __name__ == "__main__":
    res = run_scheduler()
    print(json.dumps(res, indent=2))
