# FRIDAY Media OS — Clean Rebuild & GCP Compliance Guide

## 0. Root Cause Recap (why the last project got flagged)

Nothing about your *idea* violated policy. What triggered the flag was **how** it ran:
a long-lived Streamlit web server plus FFmpeg render loops executing inside
**Cloud Shell** — an environment meant for short interactive `gcloud`/`git` sessions,
not hosting. Google's abuse detection watches for exactly that pattern
(persistent processes + heavy CPU + open web preview ports) because it's the same
signature as cryptomining, botnets, and unauthorized hosting abuse.

The fix isn't "be more careful in Cloud Shell." The fix is: **Cloud Shell never runs
anything long-lived again, ever, for any reason.** Everything below is built around
that one rule plus a compliance layer so nothing else trips a flag either.

---

## 1. Project Naming & Organization Strategy

Don't reuse `friday-media-os`. A fresh, clearly-scoped project avoids any residual
association with the flagged one and gives you clean audit logs from day one.

**Recommended structure:**

| Resource | Name | Why |
|---|---|---|
| GCP Project ID | `infosonik-media-prod` | Globally unique, ties to your actual brand (Infosonik), not a generic reused name |
| Project display name | `Infosonik Media OS — Production` | Human-readable, shows intent clearly to any Google reviewer who looks at it |
| Optional staging project | `infosonik-media-staging` | Keep experimentation OFF the production project entirely — a second flag on a shared project is worse than one on an isolated staging project |
| Artifact Registry repo | `media-pipeline` | Scoped to this system only |
| Service accounts | `sa-media-ui@...`, `sa-media-pipeline@...` | Named by function, not generic `default` |
| GCS bucket | `infosonik-media-assets-prod` | Bucket names are globally unique — pick this now before someone else takes it |

Using your real organization name in the project ID also signals to Google's
automated review systems that this is a legitimate named business project, not an
anonymous throwaway — reviewers and appeal teams read project names too.

**If you have a Google Workspace or Cloud Identity org**: create this under an
actual Organization resource, not a personal Gmail account. Org-level projects get
more consistent enforcement and a real audit trail, and appeals from
organization-owned projects are generally taken more seriously than personal
accounts with no organizational context.

---

## 2. Hard Rules (non-negotiable, write these on the wall)

1. **Cloud Shell is for `gcloud`, `git`, and file edits only.** Never `streamlit run`,
   never `python app.py`, never anything that opens a listening port or runs longer
   than a few seconds. If you need to test the UI, deploy it to Cloud Run first —
   even a throwaway revision — and test it there.
2. **Services handle requests. Jobs do batch work.** Cloud Run Jobs are explicitly
   designed for exactly your FFmpeg render workload — they're ephemeral and
   task-driven, run to completion, and support timeouts up to 168 hours (7 days)
   for long compute, versus the 60-minute cap on a Service request. Never let a
   Service (the UI) execute the render logic in-process.
3. **Set a hard billing cap before writing a single line of code.** Not a soft
   alert — a budget with an actual cap and a Cloud Function that disables billing
   if exceeded. This protects you from both accidental cost blowouts and looks
   good on an appeal ("we have proactive cost/usage controls in place").
4. **Least-privilege service accounts, one per component**, never your personal
   credentials, never a single shared `Editor`-role service account.
5. **Every deploy goes through Cloud Build**, not manual `docker push` from Cloud
   Shell — keeps the audit log clean and avoids Cloud Shell doing any heavy lifting.

---

## 3. Step-by-Step Setup (in order)

### 3.1 Create the project properly
```bash
gcloud projects create infosonik-media-prod \
  --name="Infosonik Media OS — Production" \
  --organization=YOUR_ORG_ID   # omit if no org; strongly recommended if you have one

gcloud config set project infosonik-media-prod
gcloud billing projects link infosonik-media-prod --billing-account=YOUR_BILLING_ACCOUNT_ID
```

### 3.2 Set a hard budget cap BEFORE enabling any APIs
```bash
gcloud billing budgets create \
  --billing-account=YOUR_BILLING_ACCOUNT_ID \
  --display-name="Infosonik Media Hard Cap" \
  --budget-amount=20USD \
  --threshold-rule=percent=0.5 \
  --threshold-rule=percent=0.9 \
  --threshold-rule=percent=1.0
```
Pair this with a budget-triggered Pub/Sub → Cloud Function that disables billing at
100% if you want a true hard stop rather than just an email alert. This is the
single best thing you can point to in any future appeal as evidence of
responsible, compliant usage.

### 3.3 Enable only the APIs you need
```bash
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
```

### 3.4 Create least-privilege service accounts
```bash
# UI service account — read-only where possible
gcloud iam service-accounts create sa-media-ui \
  --display-name="Media UI Service Account"

gcloud projects add-iam-policy-binding infosonik-media-prod \
  --member="serviceAccount:sa-media-ui@infosonik-media-prod.iam.gserviceaccount.com" \
  --role="roles/datastore.viewer"

gcloud projects add-iam-policy-binding infosonik-media-prod \
  --member="serviceAccount:sa-media-ui@infosonik-media-prod.iam.gserviceaccount.com" \
  --role="roles/run.developer"   # only enough to trigger Job executions

# Pipeline service account — write access, scoped only to what workers touch
gcloud iam service-accounts create sa-media-pipeline \
  --display-name="Media Pipeline Service Account"

gcloud projects add-iam-policy-binding infosonik-media-prod \
  --member="serviceAccount:sa-media-pipeline@infosonik-media-prod.iam.gserviceaccount.com" \
  --role="roles/datastore.user"

gcloud projects add-iam-policy-binding infosonik-media-prod \
  --member="serviceAccount:sa-media-pipeline@infosonik-media-prod.iam.gserviceaccount.com" \
  --role="roles/storage.objectAdmin"

gcloud projects add-iam-policy-binding infosonik-media-prod \
  --member="serviceAccount:sa-media-pipeline@infosonik-media-prod.iam.gserviceaccount.com" \
  --role="roles/aiplatform.user"
```
Never grant `roles/editor` or `roles/owner` to either. Neither account needs
Cloud Shell access, Compute Engine access, or IAM-modification rights.

### 3.5 Create the bucket and Firestore
```bash
gcloud storage buckets create gs://infosonik-media-assets-prod \
  --location=us-central1 \
  --uniform-bucket-level-access

gcloud firestore databases create --location=us-central1
```

### 3.6 Artifact Registry + Cloud Build (never build from Cloud Shell manually)
```bash
gcloud artifacts repositories create media-pipeline \
  --repository-format=docker \
  --location=us-central1

# Build via Cloud Build, not local docker build/push
gcloud builds submit --tag us-central1-docker.pkg.dev/infosonik-media-prod/media-pipeline/ui:latest -f Dockerfile.ui .
gcloud builds submit --tag us-central1-docker.pkg.dev/infosonik-media-prod/media-pipeline/pipeline:latest -f Dockerfile.pipeline .
```

### 3.7 Deploy — Service for UI, Job for pipeline
```bash
gcloud run deploy media-ui \
  --image us-central1-docker.pkg.dev/infosonik-media-prod/media-pipeline/ui:latest \
  --service-account=sa-media-ui@infosonik-media-prod.iam.gserviceaccount.com \
  --region=us-central1 \
  --min-instances=0 --max-instances=2 \
  --port=8501 --memory=1Gi \
  --allow-unauthenticated

gcloud run jobs create media-pipeline \
  --image us-central1-docker.pkg.dev/infosonik-media-prod/media-pipeline/pipeline:latest \
  --service-account=sa-media-pipeline@infosonik-media-prod.iam.gserviceaccount.com \
  --region=us-central1 \
  --memory=2Gi --cpu=2 \
  --task-timeout=1800 --max-retries=1
```

---

## 4. Monitoring — catch problems before Google does

```bash
# Alert if a Cloud Run service runs unusually long or restarts repeatedly
gcloud alpha monitoring policies create \
  --notification-channels=YOUR_CHANNEL_ID \
  --display-name="Media UI - High Restart Rate" \
  --condition-display-name="Restarts > 5 in 10 min" \
  --condition-filter='resource.type="cloud_run_revision" AND resource.label.service_name="media-ui"' \
  --condition-threshold-value=5 \
  --condition-threshold-duration=600s
```
Also turn on **Cloud Logging retention** (default 30 days is fine) so if anything
does get flagged again, you have your own timestamped evidence of what actually
ran, independent of Google's side — this is exactly the kind of detail appeal
reviewers ask for and most people can't produce quickly.

---

## 5. Pre-Launch Compliance Checklist

- [ ] Project created under org (or clearly-named personal project), not a reused/flagged one
- [ ] Billing budget with hard cap configured *before* any API is enabled
- [ ] Two separate service accounts, least-privilege roles only, no `Editor`/`Owner`
- [ ] No process in this project will ever run inside Cloud Shell beyond `gcloud`/`git`
- [ ] UI deployed as a Cloud Run **Service** (`min-instances=0`)
- [ ] Render pipeline deployed as a Cloud Run **Job**, never called in-process from the UI
- [ ] All builds go through Cloud Build, not manual Cloud Shell docker commands
- [ ] Monitoring alert configured for restart/error spikes
- [ ] Logging retention confirmed active
- [ ] Bucket uses uniform bucket-level access, not public by default
- [ ] `--allow-unauthenticated` only on the UI, never on anything with write access to GCS/Firestore

## 6. Ongoing Discipline

- Review the billing dashboard weekly for the first month — catch a runaway Job
  before it becomes a real bill or a real abuse flag.
- Never test render logic by manually SSH-ing or Cloud-Shell-running the pipeline
  container long-form — trigger it as an actual Job execution every time, even for
  a one-off test, so your usage pattern stays consistent with what you declared.
- If you ever do get a warning email again, respond within 24 hours, not after the
  suspension — the FAQ is explicit that a timely response to a *warning* is what
  prevents escalation to full suspension.

---

*This project intentionally never touches Cloud Shell for anything beyond initial
setup commands. Every long-running or compute-heavy process lives in a properly
scoped Cloud Run Service or Job from the very first deploy.*
