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

        # 1. Housekeeping: Find stuck items and fail them
        try:
            now = datetime.datetime.utcnow()
            two_hours_ago_dt = now - datetime.timedelta(hours=2)

            # Query for items not in terminal states
            terminal_states = ["COMPLETE", "FAILED", "PUBLIC", "CAPTIONS_VERIFIED", "MEMORY_UPDATED"]

            query = db.collection("content_items").where("status", "not-in", terminal_states).stream()

            for doc in query:
                data = doc.to_dict()
                created_at = data.get("created_at")
                created_at_dt = None

                if created_at:
                    if isinstance(created_at, str):
                        try:
                            created_at_dt = datetime.datetime.fromisoformat(
                                created_at.replace("Z", "+00:00")
                            ).replace(tzinfo=None)
                        except Exception:
                            created_at_dt = None
                    elif hasattr(created_at, "replace"):
                        try:
                            created_at_dt = (
                                created_at.replace(tzinfo=None)
                                if getattr(created_at, "tzinfo", None)
                                else created_at
                            )
                        except Exception:
                            created_at_dt = None

                if created_at_dt and created_at_dt < two_hours_ago_dt:
                    logger.warning(f"Marking content item {doc.id} as FAILED (stuck > 2 hours)")
                    doc.reference.update({
                        "status": "FAILED",
                        "last_error": "Timeout: stuck in non-terminal state for > 2 hours",
                        "failed_state": data.get("status"),
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
            
        # Read round-robin cursor to rotate brand ordering across runs
        cursor_doc = db.collection("scheduler_leases").document("round_robin_cursor").get()
        last_brand = cursor_doc.to_dict().get("last_dispatched_brand") if cursor_doc.exists else None

        all_brand_ids = sorted(brand_groups.keys())
        if last_brand in all_brand_ids:
            idx = all_brand_ids.index(last_brand)
            rotated_order = all_brand_ids[idx+1:] + all_brand_ids[:idx+1]
        else:
            rotated_order = all_brand_ids

        # Interleave using rotated brand order
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
            try:
                db.collection("content_items").document(selected_id).update({
                    "status": next_lock_state,
                    "updated_at": datetime.datetime.utcnow().isoformat()
                })
            except Exception as claim_err:
                logger.error(f"Failed to write claim state for {selected_id}: {claim_err}")
                selected_item = None

            if selected_item:
                try:
                    db.collection("scheduler_leases").document("round_robin_cursor").set({
                        "last_dispatched_brand": selected_data.get("brand_id"),
                        "updated_at": datetime.datetime.utcnow().isoformat()
                    })
                except Exception as cursor_err:
                    logger.warning(f"Failed to update round-robin cursor (non-fatal): {cursor_err}")
        
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
