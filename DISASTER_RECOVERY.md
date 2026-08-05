# FRIDAY Media OS — Disaster Recovery

## Data Integrity
### Firestore
*   **Backup**: Daily export to `gs://friday-media-backups/firestore`.
*   **Restore**: Use `gcloud firestore import` to restore from the latest GCS backup.

### Assets (GCS)
*   Final renders and audio are stored in `gs://friday-media-assets-prod`.
*   Retention Policy: 30 days for intermediate frames; indefinite for final renders.

## Authentication Recovery
If Secret Manager becomes corrupted or credentials are lost:
1.  Locate the YouTube Client ID/Secret in the Google Cloud Console.
2.  Re-run `youtube_auth.py` for each brand.
3.  Manually update Secret Manager keys.

## System Failure
If the `media-ui` service becomes unavailable:
1.  Check Cloud Run revision health.
2.  Redeploy using `./deploy.sh`.
3.  The `autonomous_scheduler` will continue to run as it is decoupled from the UI.
