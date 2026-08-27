import logging
import datetime
from google.cloud import firestore

from src.engine.goal_engine import GoalEngine
from src.config.brand_registry import BRAND_REGISTRY

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


def run_scheduler() -> dict:
    """
    Lightweight orchestrator:
    - Implements Global Production Lease to prevent concurrent execution overlaps
    - Runs housekeeping (fails stuck items, re-verifies PUBLIC uploads)
    - Wakes up GoalEngine for each brand using round-robin interleaving.
    """
    import uuid
    import os
    logger.info("Starting autonomous scheduler execution...")
    db = firestore.Client()
    
    execution_name = os.environ.get("CLOUD_RUN_EXECUTION", "local-run")
    owner_id = f"{execution_name}-{uuid.uuid4().hex[:6]}"
    
    # Acquire Global Production Lease
    lease_acquired = False
    transaction = db.transaction()
    
    @firestore.transactional
    def _acquire(tx):
        lease_ref = db.collection("scheduler_leases").document("production_lease")
        snapshot = lease_ref.get(transaction=tx)
        
        now = datetime.datetime.now(datetime.UTC)
        
        if snapshot.exists:
            data = snapshot.to_dict()
            expires_at_str = data.get("expires_at")
            if expires_at_str:
                try:
                    expires_at = datetime.datetime.fromisoformat(expires_at_str)
                    if expires_at.tzinfo is None:
                        expires_at = expires_at.replace(tzinfo=datetime.UTC)
                except Exception:
                    expires_at = datetime.datetime.min.replace(tzinfo=datetime.UTC)
            else:
                expires_at = datetime.datetime.min.replace(tzinfo=datetime.UTC)
            
            if now < expires_at:
                logger.info(f"Lease active: held by {data.get('owner')} until {expires_at.isoformat()}")
                return False
            else:
                logger.warning(f"Lease expired: previous owner {data.get('owner')} expired at {expires_at.isoformat()}. Recovering lease.")
        
        expires_at = now + datetime.timedelta(seconds=2100)  # 35 minutes TTL
        tx.set(lease_ref, {
            "owner": owner_id,
            "acquired_at": now.isoformat(),
            "expires_at": expires_at.isoformat()
        })
        return True

    try:
        lease_acquired = _acquire(transaction)
        if lease_acquired:
            logger.info(f"PRODUCTION_LEASE_ACQUIRED: owner={owner_id}")
        else:
            logger.info(f"PRODUCTION_LEASE_DENIED: owner={owner_id}")
            return {"status": "lease_denied"}
    except Exception as e:
        logger.error(f"Error acquiring lease: {e}")
        return {"status": "lease_error"}

    try:
        goal_engine = GoalEngine()

        # 1. Housekeeping: Find stuck items and fail/recover them
        try:
            now = datetime.datetime.utcnow()

            # State-specific timeout thresholds in minutes
            STATE_TIMEOUT_MINUTES = {
                "NEW": 240,               # 4 hours
                "TOPIC_SELECTED": 60,     # 60 min
                "SCRIPT_READY": 90,       # 90 min
                "ASSETS_READY": 15,       # 15 min
                "RENDERING": 90,          # 90 min
                "RENDERED": 15,           # 15 min
                "UPLOADING": 60,          # 60 min
                "CAPTIONS_VERIFIED": 15,  # 15 min
                "MEMORY_UPDATED": 15,     # 15 min
            }

            # Query items not in final terminal states
            terminal_states = ["COMPLETE", "FAILED"]

            query = db.collection("content_items").where("status", "not-in", terminal_states).stream()

            for doc in query:
                data = doc.to_dict()
                status = data.get("status", "NEW")

                # Parse timestamps (prefer updated_at, fallback to created_at)
                updated_at_raw = data.get("updated_at")
                created_at_raw = data.get("created_at")
                
                ref_dt = None
                raw_timestamp = updated_at_raw if (status != "NEW" and updated_at_raw) else created_at_raw
                
                if raw_timestamp:
                    if isinstance(raw_timestamp, str):
                        try:
                            ref_dt = datetime.datetime.fromisoformat(
                                raw_timestamp.replace("Z", "+00:00")
                            ).replace(tzinfo=None)
                        except Exception:
                            ref_dt = None
                    elif hasattr(raw_timestamp, "replace"):
                        try:
                            ref_dt = (
                                raw_timestamp.replace(tzinfo=None)
                                if getattr(raw_timestamp, "tzinfo", None)
                                else raw_timestamp
                            )
                        except Exception:
                            ref_dt = None

                if ref_dt:
                    age_minutes = (now - ref_dt).total_seconds() / 60.0

                    # Case A: PUBLIC state-specific 24h handling
                    if status == "PUBLIC":
                        if age_minutes >= 1440:  # 24 hours
                            yt_id = data.get("youtube_video_id")
                            if yt_id:
                                logger.info(f"Resolving stale PUBLIC item {doc.id} after 24h -> CAPTIONS_VERIFIED")
                                is_verified = data.get("youtube_verified") is True
                                doc.reference.update({
                                    "status": "CAPTIONS_VERIFIED",
                                    "youtube_verified": is_verified,
                                    "updated_at": datetime.datetime.utcnow().isoformat(),
                                    "public_timeout_resolved": True
                                })
                            else:
                                logger.warning(f"Failing stale PUBLIC item {doc.id} after 24h (no youtube_video_id)")
                                doc.reference.update({
                                    "status": "FAILED",
                                    "last_error": "PUBLIC timeout: no youtube_video_id after 24h",
                                    "failed_state": "PUBLIC",
                                    "updated_at": datetime.datetime.utcnow().isoformat()
                                })

                    # Case B: Standard in-flight states
                    elif status in STATE_TIMEOUT_MINUTES:
                        timeout_limit = STATE_TIMEOUT_MINUTES[status]
                        if age_minutes >= timeout_limit:
                            logger.warning(
                                f"Marking content item {doc.id} as FAILED (stuck in state {status} for {age_minutes:.1f}m > {timeout_limit}m)"
                            )
                            doc.reference.update({
                                "status": "FAILED",
                                "last_error": f"Timeout: stuck in state {status} for > {timeout_limit} minutes",
                                "failed_state": status,
                                "updated_at": datetime.datetime.utcnow().isoformat()
                            })

                # Reset verification flags for items incorrectly marked
                if data.get("youtube_verified") and not data.get("youtube_video_id"):
                    doc.reference.update({"youtube_verified": False})

        except Exception as e:
            logger.error(f"Error during housekeeping: {e}")



        # 2. Evaluate Goals for Each Brand and Pre-create NEW content_items
        brand_ids = list(BRAND_REGISTRY.keys())
        missing_per_brand = {}

        for brand_id in brand_ids:
            try:
                counts = goal_engine.count_for_brand(brand_id)
                missing_per_brand[brand_id] = counts["missing"]
                logger.info(
                    f"Brand {brand_id}: target={counts['daily_target']}, "
                    f"verified={counts['verified']}, active={counts['active']}, "
                    f"missing={counts['missing']}"
                )
            except Exception as e:
                logger.error(f"Error computing missing slots for {brand_id}: {e}")
                missing_per_brand[brand_id] = 0

        # Phase 1: Pre-create NEW content_items for all missing slots
        import uuid
        from src.engine.state_machine import ContentState

        for brand_id, missing_count in missing_per_brand.items():
            if missing_count > 0:
                logger.info(f"Brand {brand_id} has {missing_count} missing daily slots. Pre-creating NEW content_items...")
                for _ in range(missing_count):
                    content_id = f"{brand_id}_{uuid.uuid4().hex[:8]}"
                    doc_ref = db.collection("content_items").document(content_id)
                    doc_ref.set({
                        "brand_id": brand_id,
                        "status": ContentState.NEW.value,
                        "created_at": datetime.datetime.utcnow().isoformat(),
                        "retry_count": 0
                    })

        # Phase 1b: Recovery of interrupted states (RENDERING, UPLOADING)
        try:
            now = datetime.datetime.utcnow()
            forty_five_mins_ago = now - datetime.timedelta(minutes=45)
            
            query = db.collection("content_items").where("status", "in", ["RENDERING", "UPLOADING"]).stream()
            for doc in query:
                data = doc.to_dict()
                updated_at_str = data.get("updated_at")
                updated_at = None
                if updated_at_str:
                    try:
                        updated_at = datetime.datetime.fromisoformat(updated_at_str.replace("Z", "+00:00")).replace(tzinfo=None)
                    except Exception:
                        pass
                if not updated_at:
                    created_at = data.get("created_at")
                    if created_at:
                        if isinstance(created_at, str):
                            try:
                                updated_at = datetime.datetime.fromisoformat(created_at.replace("Z", "+00:00")).replace(tzinfo=None)
                            except Exception:
                                pass
                        elif hasattr(created_at, "replace"):
                            try:
                                updated_at = created_at.replace(tzinfo=None)
                            except Exception:
                                pass

                if updated_at and updated_at < forty_five_mins_ago:
                    status = data.get("status")
                    logger.warning(f"Recovering stuck item {doc.id} (status={status}, last updated at {updated_at.isoformat()})")
                    
                    if status == "RENDERING":
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
                            logger.info(f"Interrupted render recovery: GCS artifact exists for {doc.id}. Setting status to RENDERED.")
                            doc.reference.update({
                                "status": "RENDERED",
                                "updated_at": datetime.datetime.utcnow().isoformat()
                            })
                        else:
                            logger.info(f"Interrupted render recovery: GCS artifact absent for {doc.id}. Rolling back to ASSETS_READY.")
                            doc.reference.update({
                                "status": "ASSETS_READY",
                                "updated_at": datetime.datetime.utcnow().isoformat()
                            })
                            
                    elif status == "UPLOADING":
                        yt_id = data.get("youtube_video_id")
                        if yt_id:
                            logger.info(f"Interrupted upload recovery: YouTube video ID exists for {doc.id}. Recovering to PUBLIC.")
                            doc.reference.update({
                                "status": "PUBLIC",
                                "updated_at": datetime.datetime.utcnow().isoformat()
                            })
                        else:
                            logger.info(f"Interrupted upload recovery: YouTube video ID absent for {doc.id}. Rolling back to RENDERED.")
                            doc.reference.update({
                                "status": "RENDERED",
                                "updated_at": datetime.datetime.utcnow().isoformat()
                            })
        except Exception as e:
            logger.error(f"Error during interrupted state recovery: {e}")

        # Phase 2: Select the next active, incomplete content_item (round-robin)
        # Read round-robin cursor state from Firestore
        last_dispatched_brand = None
        try:
            cursor_ref = db.collection("scheduler_leases").document("round_robin_cursor")
            cursor_doc = cursor_ref.get()
            if cursor_doc.exists:
                last_dispatched_brand = cursor_doc.to_dict().get("last_dispatched_brand")
                logger.info(f"Loaded round-robin cursor: last_dispatched_brand={last_dispatched_brand}")
            else:
                logger.info("Round-robin cursor document does not exist. Defaulting to None.")
        except Exception as cursor_read_err:
            logger.warning(f"Failed to read round-robin cursor state: {cursor_read_err}. Defaulting to None.")

        # Build rotated brand order for interleaving
        sorted_brands = sorted(brand_ids)
        rotated_order = list(sorted_brands)
        if last_dispatched_brand in sorted_brands:
            idx = sorted_brands.index(last_dispatched_brand)
            rotated_order = sorted_brands[idx+1:] + sorted_brands[:idx+1]
            logger.info(f"Rotated brand order starting after '{last_dispatched_brand}': {rotated_order}")
        else:
            logger.info(f"Using default alphabetical brand order: {rotated_order}")

        today_date = datetime.datetime.now(datetime.UTC).date()
        docs = list(db.collection("content_items").stream())
        
        candidates = []
        for doc in docs:
            d = doc.to_dict()
            created_date = GoalEngine.normalize_to_date(d.get("created_at"))
            if created_date != today_date:
                continue
            status = d.get("status")
            if status in ["COMPLETE", "FAILED"]:
                continue
                
            is_locked = False
            if status in ["RENDERING", "UPLOADING", "PUBLIC", "CAPTIONS_VERIFIED", "MEMORY_UPDATED"]:
                updated_at_str = d.get("updated_at")
                updated_at = None
                if updated_at_str:
                    try:
                        updated_at = datetime.datetime.fromisoformat(updated_at_str.replace("Z", "+00:00")).replace(tzinfo=None)
                    except Exception:
                        pass
                if not updated_at:
                    created_at = d.get("created_at")
                    if created_at:
                        if isinstance(created_at, str):
                            try:
                                updated_at = datetime.datetime.fromisoformat(created_at.replace("Z", "+00:00")).replace(tzinfo=None)
                            except Exception:
                                pass
                        elif hasattr(created_at, "replace"):
                            try:
                                updated_at = created_at.replace(tzinfo=None)
                            except Exception:
                                pass
                if updated_at and (datetime.datetime.utcnow() - updated_at) < datetime.timedelta(minutes=45):
                    is_locked = True
                    
            if not is_locked:
                candidates.append((doc.id, d))

        # Group by brand
        brand_groups = {}
        for b_id in brand_ids:
            brand_groups[b_id] = []
            
        for cid, d in candidates:
            bid = d.get("brand_id")
            if bid in brand_groups:
                brand_groups[bid].append((cid, d))
                
        # Sort each group by created_at (FIFO)
        for b_id in brand_groups:
            brand_groups[b_id].sort(key=lambda x: x[1].get("created_at", ""))
            
        # Interleave
        interleaved = []
        max_len = max(len(brand_groups[b_id]) for b_id in brand_groups) if brand_groups else 0
        for i in range(max_len):
            for b_id in rotated_order:
                if i < len(brand_groups[b_id]):
                    interleaved.append(brand_groups[b_id][i])
                    
        selected_item = interleaved[0] if interleaved else None
        
        # Claim the selected item in Firestore BEFORE releasing the global lease
        if selected_item:
            selected_id, selected_data = selected_item
            current_status = selected_data.get("status")
            
            next_lock_state = "RENDERING"
            if current_status == "RENDERED":
                next_lock_state = "UPLOADING"
            elif current_status in ["PUBLIC", "CAPTIONS_VERIFIED", "MEMORY_UPDATED"]:
                next_lock_state = "PUBLIC"
            elif current_status == "RETRY":
                failed_state = selected_data.get("failed_state")
                if failed_state in ["PUBLIC", "CAPTIONS_VERIFIED", "MEMORY_UPDATED"]:
                    next_lock_state = "PUBLIC"
                elif failed_state == "UPLOADING":
                    next_lock_state = "UPLOADING"
                else:
                    next_lock_state = "RENDERING"
                    
            logger.info(f"Claiming selected item {selected_id}: transitioning {current_status} -> {next_lock_state}")
            claim_succeeded = False
            try:
                db.collection("content_items").document(selected_id).update({
                    "status": next_lock_state,
                    "updated_at": datetime.datetime.utcnow().isoformat()
                })
                claim_succeeded = True
            except Exception as claim_err:
                logger.error(f"Failed to write claim state for {selected_id}: {claim_err}")
                selected_item = None

            if claim_succeeded:
                selected_brand = selected_data.get("brand_id")
                if selected_brand:
                    try:
                        db.collection("scheduler_leases").document("round_robin_cursor").set({
                            "last_dispatched_brand": selected_brand,
                            "updated_at": datetime.datetime.utcnow().isoformat()
                        }, merge=True)
                        logger.info(f"Updated round-robin cursor to last_dispatched_brand={selected_brand}")
                    except Exception as cursor_write_err:
                        logger.warning(f"Failed to update round-robin cursor to '{selected_brand}': {cursor_write_err}")
        
        # Release global lease before dispatching
        if lease_acquired:
            release_transaction = db.transaction()
            
            @firestore.transactional
            def _release(tx):
                lease_ref = db.collection("scheduler_leases").document("production_lease")
                snapshot = lease_ref.get(transaction=tx)
                if snapshot.exists:
                    data = snapshot.to_dict()
                    if data.get("owner") == owner_id:
                        tx.delete(lease_ref)
                        return True
                return False
                
            try:
                success = _release(release_transaction)
                if success:
                    logger.info(f"PRODUCTION_LEASE_RELEASED: owner={owner_id}")
                    lease_acquired = False
                else:
                    logger.warning("Failed to release lease during early release: owner mismatch or lease does not exist.")
            except Exception as e:
                logger.error(f"Error during early release of lease: {e}")

        # Dispatch the worker
        if selected_item:
            selected_id, selected_data = selected_item
            brand_id = selected_data.get("brand_id")
            topic = selected_data.get("topic", "")
            logger.info(f"DISPATCHING_WORKER: brand={brand_id}, content_id={selected_id}, topic={topic}")
            try:
                from src.job_trigger import trigger_pipeline_job
                execution_name = trigger_pipeline_job(brand_id, topic, selected_id)
                logger.info(f"Successfully triggered media-pipeline execution: {execution_name}")
            except Exception as trigger_err:
                logger.error(f"Failed to trigger media-pipeline job: {trigger_err}")
        else:
            logger.info("No active, dispatchable content items found.")

    except Exception as e:
        logger.error(f"Error in scheduler execution: {e}")
        return {"status": "error", "message": str(e)}
    finally:
        if lease_acquired:
            # Release lease
            release_transaction = db.transaction()
            
            @firestore.transactional
            def _release(tx):
                lease_ref = db.collection("scheduler_leases").document("production_lease")
                snapshot = lease_ref.get(transaction=tx)
                if snapshot.exists:
                    data = snapshot.to_dict()
                    if data.get("owner") == owner_id:
                        tx.delete(lease_ref)
                        return True
                return False
                
            try:
                success = _release(release_transaction)
                if success:
                    logger.info(f"PRODUCTION_LEASE_RELEASED: owner={owner_id}")
                else:
                    logger.warning(f"Failed to release lease: owner mismatch or lease does not exist.")
            except Exception as e:
                logger.error(f"Error releasing lease: {e}")

    logger.info("Scheduler execution completed.")
    return {"status": "success"}


if __name__ == "__main__":
    run_scheduler()
