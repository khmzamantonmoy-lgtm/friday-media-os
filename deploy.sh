#!/usr/bin/env bash
set -euo pipefail

PROJECT_ID=$(gcloud config get-value project 2>/dev/null)
if [ -z "${PROJECT_ID}" ]; then
  echo "Error: No active GCP project configured in gcloud." >&2
  exit 1
fi
REGION="us-central1"
REPO="media-pipeline"
UI_SA="sa-media-ui@${PROJECT_ID}.iam.gserviceaccount.com"
PIPE_SA="sa-media-pipeline@${PROJECT_ID}.iam.gserviceaccount.com"

echo "== Setting project =="
gcloud config set project "${PROJECT_ID}"

echo "== Enabling required APIs =="
gcloud services enable \
  run.googleapis.com \
  artifactregistry.googleapis.com \
  firestore.googleapis.com \
  storage.googleapis.com \
  aiplatform.googleapis.com \
  texttospeech.googleapis.com \
  cloudbuild.googleapis.com

echo "== Creating Artifact Registry repo (skips if it exists) =="
gcloud artifacts repositories create "${REPO}" \
  --repository-format=docker \
  --location="${REGION}" || true

UI_IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO}/ui:latest"
PIPELINE_IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO}/pipeline:latest"

echo "== Building UI image =="
gcloud builds submit --config=cloudbuild-ui.yaml .

echo "== Building pipeline image =="
gcloud builds submit --config=cloudbuild-pipeline.yaml .

echo "== Deploying UI as a Cloud Run Service (scales to zero) =="
gcloud run deploy media-ui \
  --image "${UI_IMAGE}" \
  --region "${REGION}" \
  --service-account="${UI_SA}" \
  --min-instances=0 \
  --max-instances=2 \
  --port=8501 \
  --memory=1Gi \
  --set-env-vars="GCP_PROJECT_ID=${PROJECT_ID},GCP_REGION=${REGION},PIPELINE_JOB_NAME=media-pipeline,GCS_BUCKET_NAME=friday-media-assets-prod" \
  --allow-unauthenticated

echo "== Creating/updating pipeline as a Cloud Run Job (runs to completion, no listener) =="
gcloud run jobs describe media-pipeline --region "${REGION}" >/dev/null 2>&1 && \
gcloud run jobs update media-pipeline \
  --image "${PIPELINE_IMAGE}" \
  --region "${REGION}" \
  --service-account="${PIPE_SA}" \
  --memory=2Gi \
  --cpu=2 \
  --task-timeout=1800 \
  --max-retries=1 \
  --set-env-vars="GCP_PROJECT_ID=${PROJECT_ID},GCP_REGION=${REGION},GCS_BUCKET_NAME=friday-media-assets-prod" \
|| \
gcloud run jobs create media-pipeline \
  --image "${PIPELINE_IMAGE}" \
  --region "${REGION}" \
  --service-account="${PIPE_SA}" \
  --memory=2Gi \
  --cpu=2 \
  --task-timeout=1800 \
  --max-retries=1 \
  --set-env-vars="GCP_PROJECT_ID=${PROJECT_ID},GCP_REGION=${REGION},GCS_BUCKET_NAME=friday-media-assets-prod"

echo "== Done. UI URL: =="
gcloud run services describe media-ui --region "${REGION}" --format="value(status.url)"
