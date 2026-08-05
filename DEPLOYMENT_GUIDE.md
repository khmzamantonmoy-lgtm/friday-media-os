# FRIDAY Media OS — Deployment Guide

## Prerequisites
*   Google Cloud Project (e.g., `friday-media-prod`).
*   Enabled APIs: Cloud Run, Firestore, Secret Manager, Vertex AI, Text-to-Speech, YouTube Data API v3.
*   Artifact Registry repository named `media-pipeline`.

## Infrastructure Setup
1.  **Service Accounts**:
    *   `sa-media-ui`: Roles: `datastore.user`, `storage.objectViewer`, `run.developer`.
    *   `sa-media-pipeline`: Roles: `datastore.user`, `storage.objectAdmin`, `aiplatform.user`, `run.invoker`.
2.  **Secrets**:
    *   Create Secret Manager entries for each brand (e.g., `bd-threatpulse-client-secret`, `bd-threatpulse-token`).

## Automated Deployment
The `deploy.sh` script handles containerization and deployment:
```bash
# Set project context
gcloud config set project friday-media-prod

# Run deployment
./deploy.sh
```

## Manual Image Build (Cloud Build)
```bash
# Build UI
gcloud builds submit --config cloudbuild-ui.yaml .

# Build Pipeline
gcloud builds submit --config cloudbuild-pipeline.yaml .
```

## Scheduler Configuration
1.  Create a Cloud Scheduler job targeting the Autonomous Scheduler endpoint (or a Cloud Run Job trigger).
2.  Frequency: Every 1-6 hours depending on brand strategy.
