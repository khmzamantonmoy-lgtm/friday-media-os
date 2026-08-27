import datetime
from google.cloud import firestore

db = firestore.Client(project='friday-media-prod')

in_progress_statuses = [
    "QUEUED", "GENERATING", "SCRIPT_READY", "METADATA_READY",
    "VOICE_READY", "IMAGES_READY", "RENDERING"
]

now = datetime.datetime.now(datetime.timezone.utc)
timeout_threshold = now - datetime.timedelta(hours=1)

print(f"Recovery threshold time: {timeout_threshold}")

updated_count = 0
for doc in db.collection('content_queue').stream():
    d = doc.to_dict()
    status = d.get('status')
    created_at = d.get('created_at')
    
    # Handle missing created_at as very old
    is_old = False
    if created_at is None:
        is_old = True
    else:
        is_old = created_at < timeout_threshold
        
    if status in in_progress_statuses and is_old:
        content_id = doc.id
        print(f"Recovering orphaned queue item {content_id} (status={status}, created={created_at})...")
        
        # Non-destructive update on content_queue
        db.collection('content_queue').document(content_id).update({
            "status": "FAILED",
            "failure_reason": "orphaned_execution",
            "recovered_at": firestore.SERVER_TIMESTAMP,
            "updated_at": firestore.SERVER_TIMESTAMP
        })
        
        # Non-destructive update on content_items
        item_ref = db.collection('content_items').document(content_id)
        if item_ref.get().exists:
            item_ref.update({
                "status": "failed",
                "failure_reason": "orphaned_execution",
                "recovered_at": firestore.SERVER_TIMESTAMP,
                "updated_at": firestore.SERVER_TIMESTAMP
            })
            
        updated_count += 1

print(f"Successfully recovered {updated_count} orphaned records.")
