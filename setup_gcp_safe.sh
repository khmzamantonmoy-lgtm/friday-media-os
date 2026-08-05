#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# FRIDAY / Infosonik Media OS — Compliant Bootstrap
# ============================================================

PROJECT_ID=$(gcloud config get-value project 2>/dev/null)
if [ -z "${PROJECT_ID}" ]; then
  echo "❌ Error: No active GCP project configured in gcloud." >&2
  exit 1
fi

echo "🚀 Bootstrapping compliance configuration for Project: ${PROJECT_ID}"

REGION="us-central1"
REPO="media-pipeline"
BUCKET="friday-media-assets-${PROJECT_ID}"

# 1. Enable Required Services
echo "== 1. Enabling required APIs =="
gcloud services enable \
  run.googleapis.com \
  artifactregistry.googleapis.com \
  firestore.googleapis.com \
  storage.googleapis.com \
  aiplatform.googleapis.com \
  texttospeech.googleapis.com \
  cloudbuild.googleapis.com \
  billingbudgets.googleapis.com \
  logging.googleapis.com \
  monitoring.googleapis.com

# 2. Get Billing Account and Configure Budget
echo "== 2. Configuring billing budget =="
BILLING_ACCOUNT_ID=$(gcloud billing projects describe "${PROJECT_ID}" --format="value(billingAccountName)" | cut -d/ -f2)

if [ -n "${BILLING_ACCOUNT_ID}" ] && [ "${BILLING_ACCOUNT_ID}" != "null" ]; then
  echo "Linked Billing Account: ${BILLING_ACCOUNT_ID}"
  # Create a dedicated budget for this project if not already present
  gcloud billing budgets create \
    --billing-account="${BILLING_ACCOUNT_ID}" \
    --display-name="${PROJECT_ID}-budget-limit" \
    --budget-amount=20USD \
    --projects="projects/${PROJECT_ID}" \
    --threshold-rule=percent=0.5 \
    --threshold-rule=percent=0.9 \
    --threshold-rule=percent=1.0 || echo "⚠️ Budget policy may already exist or budget creation skipped."
else
  echo "⚠️ Warning: No billing account linked or cannot retrieve billing account ID."
fi

# 3. Create Least-Privilege Service Accounts
echo "== 3. Creating least-privilege service accounts =="
gcloud iam service-accounts create sa-media-ui \
  --display-name="Media UI Service Account" \
  --project="${PROJECT_ID}" || echo "sa-media-ui already exists"

gcloud iam service-accounts create sa-media-pipeline \
  --display-name="Media Pipeline Service Account" \
  --project="${PROJECT_ID}" || echo "sa-media-pipeline already exists"

UI_SA="sa-media-ui@${PROJECT_ID}.iam.gserviceaccount.com"
PIPE_SA="sa-media-pipeline@${PROJECT_ID}.iam.gserviceaccount.com"

# 4. Bind Roles (Least Privilege)
echo "== 4. Binding roles to service accounts =="
# UI SA needs datastore viewer and run developer
gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member="serviceAccount:${UI_SA}" \
  --role="roles/datastore.viewer"

gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member="serviceAccount:${UI_SA}" \
  --role="roles/run.developer"

# Pipeline SA needs datastore user, aiplatform user
gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member="serviceAccount:${PIPE_SA}" \
  --role="roles/datastore.user"

gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member="serviceAccount:${PIPE_SA}" \
  --role="roles/aiplatform.user"

# 5. Storage Bucket (Uniform Bucket-Level Access)
echo "== 5. Creating and securing GCS bucket =="
if gcloud storage buckets describe "gs://${BUCKET}" >/dev/null 2>&1; then
  echo "Bucket gs://${BUCKET} already exists."
else
  gcloud storage buckets create "gs://${BUCKET}" --location="${REGION}"
fi

gcloud storage buckets update "gs://${BUCKET}" --uniform-bucket-level-access

# Grant GCS permission at the bucket level (Least Privilege!)
gcloud storage buckets add-iam-policy-binding "gs://${BUCKET}" \
  --member="serviceAccount:${PIPE_SA}" \
  --role="roles/storage.objectAdmin"

# 6. Firestore Database and Delete Protection
echo "== 6. Checking Firestore and enabling delete protection =="
if gcloud firestore databases describe >/dev/null 2>&1; then
  echo "Firestore database is already initialized."
else
  gcloud firestore databases create --location="${REGION}" --type=firestore-native
fi

# Enable delete-protection to protect database
gcloud firestore databases update --database='(default)' --delete-protection

# 7. Artifact Registry Repo
echo "== 7. Setting up Artifact Registry =="
gcloud artifacts repositories create "${REPO}" \
  --repository-format=docker \
  --location="${REGION}" || echo "Artifact repository already exists"

# 8. Seed Firestore brands collection
echo "== 8. Seeding brands collection in Firestore =="
python3 -c "
import sys
sys.path.insert(0, '.')
from src.config.firestore_schema import get_db, seed_brands
db = get_db('${PROJECT_ID}')
seed_brands(db)
print('Brands seeded successfully.')
" || echo "⚠️ Firestore seeding failed. Make sure firestore is active."

echo "🎉 Compliance Bootstrap complete for project ${PROJECT_ID}!"
