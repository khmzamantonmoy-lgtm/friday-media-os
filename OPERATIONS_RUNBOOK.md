# FRIDAY Media OS — Operations Runbook

## Dashboard Monitoring
The **Operations Center** is the primary source of truth.
*   **Green (Nominal)**: System is operating within quotas.
*   **Yellow (Degraded)**: Recent job failures (e.g., 429 errors). System is retrying.
*   **Red (Critical)**: Success rate below 50% or IAM failures.

## Emergency Procedures
### 1. Stopping Production
Toggle the **Emergency Pause** switch on the Home dashboard. This halts the Autonomous Engine and prevents new jobs from triggering.

### 2. Manual Trigger
Use the **Force Production Cycle** button to initiate an immediate research and production run across all brands.

## Handling Common Issues
### 429 RESOURCE_EXHAUSTED
*   **Cause**: Vertex AI or Gemini API quota exceeded.
*   **Fix**: None required. System uses Exponential Backoff (5 attempts). If failures persist, check GCP Quota Console.

### Authentication Failures
*   **Cause**: OAuth token revoked or expired beyond refresh capability.
*   **Fix**: Use the `src/auth/youtube_auth.py` script locally to generate a new token and push it to Secret Manager.

## Log Access
View detailed worker logs in the **Google Cloud Logging** console under:
*   `resource.type="cloud_run_job"`
*   `resource.type="cloud_run_revision"`
