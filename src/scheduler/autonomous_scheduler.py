import os
import json
import datetime
import logging
import pytz
from google.cloud import firestore
from src.job_trigger import trigger_pipeline_job
from src.workers.youtube_worker import upload_video
from src.agents.google_agent_client import GoogleAgentClient
from src.verification.verification_layer import VerificationLayer

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


def run_scheduler() -> dict:
    """
    Orchestrates one autonomous cycle using Google Agent Platform + Verification Layer:
    1. Scan READY content queue items -> schedule them.
    2. Check brand daily quotas -> invoke brand Google Agent -> verify package -> trigger pipeline.
    3. Auto-publish due pending posts.
    """
    logger.info("Starting autonomous scheduler execution...")
    db = firestore.Client()
    agent_client = GoogleAgentClient()
    verifier = VerificationLayer()

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
            title = c_data.get("seo_title") or (titles[0] if titles else item.get("topic", "Video Post"))
            caption = c_data.get("caption") or c_data.get("description", "")
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
                    "agent_name": c_data.get("agent_name", "Autonomous AI"),
                    "quality_score": c_data.get("quality_score", 0.9),
                    "confidence": c_data.get("confidence", 0.9),
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

            # Count today's scheduled posts
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

            # Count in-progress items
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
                f"Brand {brand_id} has {remaining_slots} open slot(s) today. Invoking Google Agent..."
            )

            # Fetch memory document
            mem_doc = db.collection("brand_memory").document(brand_id).get()
            memory_data = mem_doc.to_dict() if mem_doc.exists else {}

            # Check Editorial Calendar if strategy is hybrid/calendar
            calendar_topic = None
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
                    calendar_topic = cal_doc.to_dict().get("topic")
                    db.collection("editorial_calendar").document(
                        cal_doc.id
                    ).update(
                        {
                            "processed": True,
                            "status": "processed",
                            "updated_at": firestore.SERVER_TIMESTAMP,
                        }
                    )
                    logger.info(f"Retrieved assignment from calendar: '{calendar_topic}'")

            # Invoke Agent with up to 2 retries if verification fails
            agent_package = None
            verification_res = None

            for attempt in range(2):
                package = agent_client.invoke_agent(
                    brand_id=brand_id,
                    brand_profile=profile,
                    brand_memory=memory_data,
                    calendar_topic=calendar_topic,
                )
                v_res = verifier.verify_decision(package, profile, memory_data)
                if v_res.passed:
                    agent_package = package
                    verification_res = v_res
                    break
                logger.warning(
                    f"Attempt {attempt+1}: Verification rejected package ({v_res.reason}). Retrying..."
                )

            if not agent_package or not verification_res or not verification_res.passed:
                logger.error(f"Abandoning generation for brand {brand_id}: Verification failed after retries.")
                results["errors"].append(f"Brand {brand_id}: Verification failed ({verification_res.reason if verification_res else 'Unknown'})")
                continue

            topic = agent_package.get("topic")
            source = "calendar" if calendar_topic else "agent"
            content_id = f"auto_{brand_id}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"

            # Store rich decision package in content_items
            db.collection("content_items").document(content_id).set(
                {
                    "brand_id": brand_id,
                    "topic": topic,
                    "status": "draft",
                    "source": source,
                    "agent_name": agent_package.get("agent_name"),
                    "category": agent_package.get("category"),
                    "editorial_reasoning": agent_package.get("editorial_reasoning"),
                    "confidence": agent_package.get("confidence"),
                    "quality_score": agent_package.get("quality_score"),
                    "verification_status": verification_res.status,
                    "verification_sources": agent_package.get("verification_sources", []),
                    "similarity_score": verification_res.metrics.get("effective_similarity"),
                    "seo_title": agent_package.get("seo_title"),
                    "caption": agent_package.get("description"),
                    "hashtags": agent_package.get("hashtags", []),
                    "cta": agent_package.get("cta"),
                    "script": agent_package.get("script_narration"),
                    "scene_plan": agent_package.get("scene_plan", []),
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
                    "agent_name": agent_package.get("agent_name"),
                    "quality_score": agent_package.get("quality_score"),
                    "created_at": firestore.SERVER_TIMESTAMP,
                    "updated_at": firestore.SERVER_TIMESTAMP,
                }
            )

            trigger_pipeline_job(brand_id, topic, content_id)
            results["triggered"].append(content_id)
            logger.info(
                f"Triggered pipeline run for {content_id} via {agent_package.get('agent_name')} (topic: '{topic}')"
            )

        except Exception as e:
            logger.exception(f"Failed to process brand {brand_doc.id}")
            results["errors"].append(f"Brand generation error: {e}")

    # ── STEP 3: Auto-publish due posts ────────────────────────────────────────
    now_utc = datetime.datetime.now(pytz.UTC)
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
