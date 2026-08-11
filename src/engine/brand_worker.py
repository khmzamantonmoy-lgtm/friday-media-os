import logging
import datetime
import uuid
from google.cloud import firestore

from src.engine.state_machine import ContentState, StateMachine
from src.engine.retry_manager import with_retry
from src.engine.semantic_memory import SemanticMemory
from src.engine.publication_verifier import PublicationVerifier
from src.engine.metrics_service import MetricsService
from src.config.brand_registry import get_brand_config

from src.workers.script_worker import generate_script
from src.workers.voice_worker import synthesize_voice
from src.workers.image_worker import generate_images
from src.workers.render_worker import render_video
from src.workers.youtube_worker import upload_video
from src.workers.metadata_worker import generate_metadata

try:
    from src.atlas.orchestrator import ATLASOrchestrator
    from src.atlas.config import ATLAS_SHADOW_MODE
    _ATLAS_AVAILABLE = True
except ImportError:
    _ATLAS_AVAILABLE = False
    ATLAS_SHADOW_MODE = True

logger = logging.getLogger(__name__)

class BrandWorker:
    def __init__(self):
        self.db = firestore.Client()
        self.metrics = MetricsService()
        self.verifier = PublicationVerifier()
        self._atlas: "ATLASOrchestrator | None" = None
        if _ATLAS_AVAILABLE:
            try:
                self._atlas = ATLASOrchestrator()
                logger.info("ATLAS orchestrator initialised (shadow_mode=%s)", ATLAS_SHADOW_MODE)
            except Exception as atlas_init_err:
                logger.warning("ATLAS orchestrator failed to initialise: %s", atlas_init_err)

    def run_cycle_for_item(self, content_id: str):
        """
        Executes the production cycle for a single pre-created content item.
        """
        doc_ref = self.db.collection("content_items").document(content_id)
        doc = doc_ref.get()
        if not doc.exists:
            logger.error(f"Content item {content_id} not found in Firestore.")
            return
            
        data = doc.to_dict()
        brand_id = data.get("brand_id")
        
        # Determine brand
        brand = get_brand_config(brand_id)
        if not brand:
            logger.error(f"Brand {brand_id} not found in registry.")
            return
        brand = dict(brand)  # defensive copy
        brand["id"] = brand_id

        memory = SemanticMemory(brand_id)
        today_iso = datetime.datetime.utcnow().date().isoformat()
        
        self._process_content(content_id, brand, memory, today_iso)

    def run_cycle(self, brand_id: str):
        """
        Executes one full cycle of generation for the brand, or resumes in-flight active work.
        """
        from src.engine.goal_engine import GoalEngine
        today_iso = datetime.datetime.utcnow().date().isoformat()
        today_date = datetime.datetime.now(datetime.UTC).date()
        
        # Determine brand
        brand = get_brand_config(brand_id)
        if not brand:
            logger.error(f"Brand {brand_id} not found in registry.")
            return
        brand = dict(brand)  # defensive copy
        brand["id"] = brand_id

        memory = SemanticMemory(brand_id)
        
        resumable_item = self._find_resumable_item(brand_id, today_date)

        if resumable_item:
            content_id, data = resumable_item
            logger.info(f"RESUMING_IN_FLIGHT_WORK: brand={brand_id}, content_id={content_id}, state={data.get('status')}")
        else:
            topic = self._generate_topic(brand, memory)
            if not topic:
                logger.warning(f"Failed to generate unique topic for {brand_id}")
                self.metrics.increment_metric(brand_id, today_iso, "duplicate_rejections")
                return
                
            content_id = f"{brand_id}_{uuid.uuid4().hex[:8]}"
            
            doc_ref = self.db.collection("content_items").document(content_id)
            doc_ref.set({
                "brand_id": brand_id,
                "topic": topic,
                "status": ContentState.NEW.value,
                "created_at": datetime.datetime.utcnow().isoformat(),
                "retry_count": 0
            })

        self._process_content(content_id, brand, memory, today_iso)

    def _find_resumable_item(self, brand_id: str, today_date) -> tuple[str, dict] | None:
        """Finds the highest priority resumable item for the brand today."""
        from src.engine.goal_engine import GoalEngine
        resumable_statuses = {
            "PUBLIC", "RETRY", "SCRIPT_READY", "ASSETS_READY", "RENDERING", "RENDERED", "UPLOADING"
        }
        
        docs = list(self.db.collection("content_items").where("brand_id", "==", brand_id).stream())
        candidates = []
        for doc in docs:
            data = doc.to_dict()
            created_date = GoalEngine.normalize_to_date(data.get("created_at"))
            if created_date == today_date and data.get("status") in resumable_statuses:
                priority = self._get_resumable_priority(data)
                candidates.append((priority, doc.id, data))
                
        if not candidates:
            return None
            
        candidates.sort(key=lambda x: (x[0], x[2].get("created_at", "")))
        return candidates[0][1], candidates[0][2]

    def _get_resumable_priority(self, data: dict) -> int:
        status = data.get("status")
        failed_state = data.get("failed_state")
        yt_id = data.get("youtube_video_id")
        
        if yt_id and (status == "PUBLIC" or (status == "RETRY" and failed_state == "PUBLIC")):
            return 1
        if status == "UPLOADING":
            return 2
        if status == "RENDERED":
            return 3
        if status == "RENDERING":
            return 4
        if status == "ASSETS_READY":
            return 5
        if status == "SCRIPT_READY":
            return 6
        if status == "RETRY" and failed_state:
            return 7
        return 8

    def _generate_topic(self, brand: dict, memory: SemanticMemory) -> str:
        from src.config.ai_request_manager import AIRequestManager
        try:
            ai_manager = AIRequestManager()

            display_name = brand.get('display_name', 'this channel')
            content_angle = brand.get('content_angle', '')
            audience = brand.get('audience', '')
            categories = ', '.join(brand.get('categories', []))
            avoid_topics = ', '.join(brand.get('avoid_topics', []))
            preferred_keywords = ', '.join(brand.get('preferred_keywords', []))
            tone = brand.get('tone', '')

            prompt = (
                f"You are the content strategist for '{display_name}', "
                f"a channel with this specific purpose:\n"
                f"{content_angle}\n\n"
                f"Target audience: {audience}\n"
                f"Categories: {categories}\n"
                f"Preferred keyword themes: {preferred_keywords}\n"
                f"Tone: {tone}\n"
                f"NEVER suggest topics about: {avoid_topics}\n\n"
                f"Propose ONE specific, on-brand video topic idea that "
                f"strictly fits this channel's actual purpose above. "
                f"Do not suggest generic, unrelated, or novelty topics. "
                f"Provide ONLY the topic, no explanation."
            )

            def _op(client):
                response = client.models.generate_content(
                    model='gemini-2.5-flash',
                    contents=prompt,
                )
                return response.text.strip()

            topic = ai_manager.execute(_op)

            if memory.check_duplicate(topic):
                return None
            return topic
        except Exception as e:
            logger.error(f"Error generating topic: {e}")
            return None

    def _update_state(self, doc_ref, current_state: ContentState, next_state: ContentState, data: dict = None):
        if not StateMachine.can_transition(current_state, next_state):
            raise ValueError(f"Invalid transition from {current_state} to {next_state}")
        
        payload = {"status": next_state.value, "updated_at": datetime.datetime.utcnow().isoformat()}
        if data:
            payload.update(data)
        doc_ref.update(payload)
        return next_state

    def _process_content(self, content_id: str, brand: dict, memory: SemanticMemory, today_iso: str):
        doc_ref = self.db.collection("content_items").document(content_id)
        doc = doc_ref.get()
        if not doc.exists:
            return
        
        data = doc.to_dict()
        current_state = ContentState(data.get("status", ContentState.NEW.value))
        topic = data.get("topic")
        brand_id = brand["id"]

        # Decouple YouTube: If upload has succeeded (already in PUBLIC or retry from PUBLIC), skip media/upload
        is_uploaded = (current_state == ContentState.PUBLIC) or (current_state == ContentState.RETRY and data.get("failed_state") == "PUBLIC")
        if is_uploaded and data.get("youtube_video_id"):
            logger.info(f"[{content_id}] Video already uploaded (youtube_video_id={data.get('youtube_video_id')}). Jumping to PUBLIC.")
            if current_state != ContentState.PUBLIC:
                current_state = self._update_state(doc_ref, current_state, ContentState.PUBLIC)

        try:
            if current_state == ContentState.RETRY:
                failed_state_str = data.get("failed_state")
                if failed_state_str:
                    try:
                        current_state = ContentState(failed_state_str)
                        logger.info(f"[{content_id}] Resuming retry item from failed_state: {current_state}")
                    except Exception:
                        current_state = ContentState.NEW
                else:
                    current_state = ContentState.NEW

            if current_state == ContentState.RENDERING:
                final_uri = data.get("final_video_uri")
                exists = False
                if final_uri and final_uri.startswith("gs://"):
                    try:
                        from google.cloud import storage
                        storage_client = storage.Client()
                        bucket_name = final_uri.split("/")[2]
                        blob_name = "/".join(final_uri.split("/")[3:])
                        bucket = storage_client.bucket(bucket_name)
                        blob = bucket.blob(blob_name)
                        exists = blob.exists()
                    except Exception as gcs_err:
                        logger.error(f"Error checking GCS for {final_uri}: {gcs_err}")
                
                if exists:
                    logger.info(f"[{content_id}] Interrupted render recovery: GCS artifact exists. Setting status to RENDERED.")
                    current_state = self._update_state(doc_ref, current_state, ContentState.RENDERED)
                else:
                    logger.info(f"[{content_id}] Interrupted render recovery: GCS artifact absent. Rolling back to ASSETS_READY.")
                    current_state = self._update_state(doc_ref, current_state, ContentState.ASSETS_READY)

            if current_state == ContentState.UPLOADING:
                yt_id = data.get("youtube_video_id")
                exists = False
                if yt_id:
                    try:
                        from src.engine.publication_verifier import PublicationVerifier
                        verifier = PublicationVerifier()
                        ver_status = verifier.verify_status(content_id, yt_id, brand_id)
                        if ver_status in ["VERIFIED", "PENDING"]:
                            exists = True
                    except Exception as yt_err:
                        logger.error(f"Error checking YouTube status: {yt_err}")
                
                if exists:
                    logger.info(f"[{content_id}] Interrupted upload recovery: YouTube upload exists. Setting status to PUBLIC.")
                    current_state = self._update_state(doc_ref, current_state, ContentState.PUBLIC)
                else:
                    logger.info(f"[{content_id}] Interrupted upload recovery: YouTube upload absent. Rolling back to RENDERED.")
                    current_state = self._update_state(doc_ref, current_state, ContentState.RENDERED)

            # Prerequisite verification & rollbacks to correct starting state
            if current_state == ContentState.RENDERED and not data.get("final_video_uri"):
                logger.info(f"[{content_id}] RENDERED but missing final_video_uri. Rolling back to ASSETS_READY.")
                current_state = ContentState.ASSETS_READY

            if current_state == ContentState.ASSETS_READY and (not data.get("audio_uri") or not data.get("image_uris")):
                if not data.get("script"):
                    logger.info(f"[{content_id}] ASSETS_READY but missing script. Rolling back to NEW.")
                    current_state = ContentState.NEW
                else:
                    logger.info(f"[{content_id}] ASSETS_READY but missing assets. Rolling back to SCRIPT_READY.")
                    current_state = ContentState.SCRIPT_READY

            if current_state == ContentState.SCRIPT_READY and not data.get("script"):
                logger.info(f"[{content_id}] SCRIPT_READY but missing script. Rolling back to NEW.")
                current_state = ContentState.NEW

            if current_state == ContentState.TOPIC_SELECTED and not data.get("topic"):
                logger.info(f"[{content_id}] TOPIC_SELECTED but missing topic. Rolling back to NEW.")
                current_state = ContentState.NEW

            if current_state == ContentState.NEW:
                if not topic:
                    topic = self._generate_topic(brand, memory)
                    if not topic:
                        raise RuntimeError("Failed to generate unique topic or duplicate detected.")
                current_state = self._update_state(doc_ref, current_state, ContentState.TOPIC_SELECTED, {"topic": topic})
                data["topic"] = topic

            if current_state == ContentState.TOPIC_SELECTED:
                # ── ATLAS Strategic Brief Injection (Shadow Mode safe) ─────────
                atlas_brief = None
                if self._atlas:
                    try:
                        brand_memory_dict = memory.get_memory() if hasattr(memory, "get_memory") else {}
                        atlas_brief = self._atlas.generate_content_brief(
                            brand_id, brand_memory_dict, existing_topic=topic
                        )
                        logger.info(
                            "[ATLAS] Brief generated for %s: category=%s, topic='%s'",
                            brand_id,
                            atlas_brief.portfolio_category.value,
                            atlas_brief.topic,
                        )
                        # QA governance gate (Shadow Mode = observe only)
                        # Full QA runs against the specialist output after _execute_script.
                    except Exception as atlas_brief_err:
                        logger.warning("[ATLAS] Brief generation failed (%s). Continuing without brief.", atlas_brief_err)
                        atlas_brief = None
                # ── End ATLAS Brief Injection ──────────────────────────────────

                script = self._execute_script(brand, topic, atlas_brief=atlas_brief)
                metadata = self._execute_metadata(script, brand)
                current_state = self._update_state(
                    doc_ref, 
                    current_state, 
                    ContentState.SCRIPT_READY, 
                    {"script": script, "metadata": metadata}
                )
                data["script"] = script
                data["metadata"] = metadata

            if current_state == ContentState.SCRIPT_READY:
                audio_uri = self._execute_voice(data["script"]["narration"], brand_id, brand.get("voice_id", "default"), content_id)
                image_uris = self._execute_images(data["script"]["visual_prompts"], brand, content_id)
                
                current_state = self._update_state(
                    doc_ref, 
                    current_state, 
                    ContentState.ASSETS_READY, 
                    {"audio_uri": audio_uri, "image_uris": image_uris}
                )
                data["audio_uri"] = audio_uri
                data["image_uris"] = image_uris

            if current_state == ContentState.ASSETS_READY:
                current_state = self._update_state(doc_ref, current_state, ContentState.RENDERING)
                
                import time
                render_start = time.time()
                final_uri, srt_uri = self._execute_render(data["script"], data["audio_uri"], data["image_uris"], brand_id, content_id)
                render_duration = time.time() - render_start
                logger.info(f"RENDER_COMPLETED: content_id={content_id}, duration={render_duration:.2f}s")
                
                current_state = self._update_state(
                    doc_ref, 
                    current_state, 
                    ContentState.RENDERED, 
                    {"final_video_uri": final_uri, "srt_uri": srt_uri}
                )
                data["final_video_uri"] = final_uri
                data["srt_uri"] = srt_uri

            if current_state == ContentState.RENDERED:
                current_state = self._update_state(doc_ref, current_state, ContentState.UPLOADING)
                metadata = data.get("metadata", {})
                
                import time
                upload_start = time.time()
                video_url = self._execute_upload(
                    brand_id, content_id, data["final_video_uri"], 
                    metadata.get("title_suggestions", [topic])[0],
                    metadata.get("caption", ""),
                    metadata.get("hashtags", []),
                    data["srt_uri"]
                )
                upload_duration = time.time() - upload_start
                logger.info(f"YOUTUBE_UPLOAD_COMPLETED: content_id={content_id}, duration={upload_duration:.2f}s")
                
                video_id = video_url.split("watch?v=")[1].split("&")[0] if "watch?v=" in video_url else video_url
                current_state = self._update_state(
                    doc_ref, 
                    current_state, 
                    ContentState.PUBLIC, 
                    {"youtube_video_id": video_id}
                )
                data["youtube_video_id"] = video_id

            if current_state == ContentState.PUBLIC:
                yt_id = data.get("youtube_video_id")
                if yt_id:
                    import time
                    verify_start = time.time()
                    ver_status = self.verifier.verify_status(content_id, yt_id, brand_id)
                    verify_duration = time.time() - verify_start
                    logger.info(f"YOUTUBE_VERIFICATION_COMPLETED: content_id={content_id}, duration={verify_duration:.2f}s")
                    if ver_status == "VERIFIED":
                        current_state = self._update_state(doc_ref, current_state, ContentState.CAPTIONS_VERIFIED)
                    elif ver_status == "PENDING":
                        logger.info(f"[{content_id}] Video is still pending processing on YouTube. Exiting worker.")
                        return
                    else:
                        logger.warning(f"[{content_id}] Verification failed.")
                        return
                else:
                    logger.error(f"[{content_id}] youtube_video_id is missing in PUBLIC state.")
                    return

            if current_state == ContentState.CAPTIONS_VERIFIED:
                memory.add_memory(content_id, topic)
                current_state = self._update_state(doc_ref, current_state, ContentState.MEMORY_UPDATED)

            if current_state == ContentState.MEMORY_UPDATED:
                current_state = self._update_state(doc_ref, current_state, ContentState.COMPLETE)
                self.metrics.increment_metric(brand_id, today_iso, "published")
                logger.info(f"[{content_id}] Production cycle fully completed.")
                return

        except Exception as e:
            logger.exception(f"Error in brand worker for {content_id}")
            self._handle_failure(doc_ref, doc.to_dict(), current_state, str(e), brand_id, today_iso)


    def _handle_failure(self, doc_ref, data: dict, state: ContentState, error_msg: str, brand_id: str, today_iso: str):
        retries = data.get("retry_count", 0)
        if retries < 5:
            doc_ref.update({
                "status": ContentState.RETRY.value,
                "retry_count": retries + 1,
                "last_error": error_msg,
                "failed_state": state.value
            })
            self.metrics.increment_metric(brand_id, today_iso, "retries")
        else:
            doc_ref.update({
                "status": ContentState.FAILED.value,
                "last_error": error_msg,
                "failed_state": state.value
            })
            self.metrics.increment_metric(brand_id, today_iso, "failed")
            self.db.collection("dead_letter_queue").add({
                "content_id": doc_ref.id,
                "brand_id": brand_id,
                "state": state.value,
                "error": error_msg,
                "timestamp": firestore.SERVER_TIMESTAMP
            })

    @with_retry(max_retries=5, base_delay=2.0)
    def _execute_script(self, brand, topic, atlas_brief=None):
        """
        Generates a content script.
        When an ATLAS ContentBrief is supplied, routes through invoke_agent_with_brief
        so the specialist receives strategic context while preserving brand identity.
        Falls back to standard generate_script on any error.
        """
        if atlas_brief and _ATLAS_AVAILABLE:
            try:
                from src.agents.google_agent_client import GoogleAgentClient
                brand_id = brand.get("id", "")
                agent_client = GoogleAgentClient()
                # Minimal memory stub — SemanticMemory is already in scope above
                return agent_client.invoke_agent_with_brief(
                    brand_id,
                    brand,
                    {},  # brand_memory: full memory passed at brief-generation time
                    atlas_brief,
                )
            except Exception as atlas_script_err:
                logger.warning(
                    "[ATLAS] invoke_agent_with_brief failed (%s). Falling back to generate_script.",
                    atlas_script_err,
                )
        return generate_script(brand, topic)


    @with_retry(max_retries=5, base_delay=2.0)
    def _execute_metadata(self, script, brand):
        return generate_metadata(script, brand)

    @with_retry(max_retries=5, base_delay=2.0)
    def _execute_voice(self, narration, brand_id, voice_id, content_id):
        return synthesize_voice(narration, brand_id, voice_id, content_id)

    @with_retry(max_retries=5, base_delay=2.0)
    def _execute_images(self, visual_prompts, brand, content_id):
        return generate_images(visual_prompts, brand, content_id)

    @with_retry(max_retries=3, base_delay=5.0)
    def _execute_render(self, script, audio_uri, image_uris, brand_id, content_id):
        return render_video(script, audio_uri, image_uris, brand_id, content_id)

    @with_retry(max_retries=5, base_delay=10.0)
    def _execute_upload(self, channel, content_id, video_gs_uri, title, description, hashtags, srt_gs_uri):
        return upload_video(channel, content_id, video_gs_uri, title, description, hashtags, srt_gs_uri)
