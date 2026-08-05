# Pre-Remediation Operational Validation Report
**Current Project:** `friday-media-prod`  
**Current Account:** `khmzamantonmoy@gmail.com`  
**Current Region:** `us-central1`  
**Status:** Verification Report Completed — Awaiting Approval  

This report documents the current, verified operational state of the production GCP project `friday-media-prod` prior to the execution of any remediation steps or deployments.

---

## 1. CLOUD RUN SERVICE: `media-ui`
*   **Service exists:** YES. Serves the Streamlit web dashboard.
*   **Latest revision is Ready:** YES. Latest revision is `media-ui-00003-kpt`, which transitioned to a Ready status on `2026-08-01T19:10:08.352531Z`.
*   **Container starts correctly:** YES. Verified by stdout logs indicating server binding: `You can now view your Streamlit app in your browser.`
*   **Health status:** HEALTHY. Conditions `Ready`, `ConfigurationsReady`, and `RoutesReady` are all set to `True`.
*   **Startup logs:** Verified. The service container successfully initializes and binds to port `8501`.
*   **Runtime logs:** Verified. Displays incoming request logs (WebSocket upgrades and health queries). However, when a user attempts to generate content, the logs record an uncaught exception:
    `google.api_core.exceptions.PermissionDenied: 403 Missing or insufficient permissions.`
*   **Environment variables:**
    *   `GCP_PROJECT_ID` = `"friday-media-prod"`
    *   `GCP_REGION` = `"us-central1"`
    *   `PIPELINE_JOB_NAME` = `"media-pipeline"`
*   **Service Account:** `sa-media-ui@friday-media-prod.iam.gserviceaccount.com`
*   **Memory:** `1Gi`
*   **CPU:** `1` (1000m)
*   **Concurrency:** `80`
*   **Ingress:** `all` (Allows public internet access)
*   **Authentication:** Public unauthenticated access allowed (`allUsers` bound to `roles/run.invoker`).
*   **URL accessibility:** YES. Accessible at `https://media-ui-ylzb4xvega-uc.a.run.app`.

---

## 2. CLOUD RUN JOB: `media-pipeline`
*   **Job exists:** YES. Orchestrates the video generation pipeline.
*   **Image exists:** YES. Located at `us-central1-docker.pkg.dev/friday-media-prod/media-pipeline/pipeline:latest`.
*   **Service Account:** `sa-media-pipeline@friday-media-prod.iam.gserviceaccount.com`
*   **Timeout:** 1800 seconds.
*   **CPU:** 2
*   **Memory:** 2Gi
*   **Environment variables:**
    *   `BRAND_ID` = `"wealthwise"`
    *   `GCP_PROJECT_ID` = `"friday-media-prod"`
    *   `GCP_REGION` = `"us-central1"`
*   **Last execution:** `media-pipeline-pb8r9`, created on `2026-08-02T05:39:31Z` and completed on `2026-08-02T05:45:48Z`.
*   **Failure reason:** None.
*   **Logs:** Verified. Executed script writing, text-to-speech creation, image generation, and moviepy compilation.
*   **Exit code:** `0` (Logs show `Container called exit(0)`).
*   **Operational Capability:** The job is capable of executing successfully to completion when triggered manually or via gcloud.

---

## 3. FIRESTORE DATABASE
*   **Database exists:** YES. Location: `projects/friday-media-prod/databases/(default)`.
*   **Native mode:** YES. `type: FIRESTORE_NATIVE` is active.
*   **Read permissions:** YES. Verified via query stream from the local shell environment.
*   **Write permissions:** PARTIAL. Writes succeed from local Cloud Shell and the Cloud Run Job, but FAIL from the Cloud Run UI service due to IAM scope mismatches.
*   **Collections expected by the application:**
    *   `brands` (Present, contains 5 documents).
    *   `content_items` (Present, contains 15 documents).
*   **Connectivity from Cloud Run:** FAIL. Attempts to write content items trigger a Firestore write Permission Denied error.
*   **Connectivity from Cloud Run Job:** PASS. Successfully writes pipeline status logs (`STATUS_PUBLISHED`) to documents.

---

## 4. CLOUD STORAGE: `gs://friday-media-assets-prod`
*   **Bucket exists:** YES.
*   **Region:** `us-central1`.
*   **Uniform bucket access:** YES. `uniform_bucket_level_access: true` is set.
*   **IAM:** Verified. Service account `sa-media-pipeline` possesses the project-level `roles/storage.objectAdmin` role.
*   **Read capability:** YES. Verified by listing bucket folders.
*   **Write capability:** YES. Verified by the job writing output files.
*   **Application bucket configuration:** Hardcoded to `friday-media-assets-prod` in worker scripts.
*   **Bucket name consistency throughout the codebase:** **INCONSISTENT** at the code level (hardcoded bucket strings instead of environment lookups), but operationally consistent with the `friday-media-prod` project bucket name.

---

## 5. ARTIFACT REGISTRY: `media-pipeline`
*   **Repository exists:** YES. Location: `us-central1`, Format: `DOCKER`.
*   **UI image exists:** YES. Latest digest is `sha256:47bd45aa9e4f0734e909a4ce1f14f82662b9fe0c9f6a8bfed4efc384fa690010`.
*   **Pipeline image exists:** YES. Latest digest is `sha256:3d5617976c35009dc0b6e0f844274e6a2affef850747b5bc2f7d637d9833ec22`.
*   **Latest image digests:** Verified.
*   **Deployment matches latest image:** YES. The deployed revisions run container images built from the registry repository.

---

## 6. IAM SERVICES AND BINDINGS
*   **Service Accounts Checked:**
    1.  `sa-media-ui@friday-media-prod.iam.gserviceaccount.com` (Active).
    2.  `sa-media-pipeline@friday-media-prod.iam.gserviceaccount.com` (Active).
    3.  `1021146842794-compute@developer.gserviceaccount.com` (Default Compute SA, Active).
*   **Required Permissions Existence:**
    *   `sa-media-pipeline` has `roles/aiplatform.user`, `roles/datastore.user`, and `roles/storage.objectAdmin` (Capable).
    *   `sa-media-ui` has `roles/run.developer` and `roles/datastore.viewer` (**INSUFFICIENT**).
*   **Missing permissions:**
    *   `sa-media-ui` is missing Firestore write access. It is bound to `roles/datastore.viewer` (read-only), which causes the Streamlit UI to crash when attempting to write new content generation records (`create_content_item`). It requires `roles/datastore.user`.
    *   The deployer/runner identity lacks `roles/iam.serviceAccountUser` (`iam.serviceAccounts.actAs` permission) on the user-managed service accounts.
*   **Excessive permissions:**
    *   `sa-media-pipeline` has project-level `roles/storage.objectAdmin` rather than bucket-scoped permissions.
*   **Incorrect bindings:**
    *   `sa-media-ui` is bound to `roles/datastore.viewer` instead of `roles/datastore.user`.

---

## 7. APPLICATION CONFIGURATION
*   **Environment variables:** Active on services, but contain hardcoded parameters in the repository code.
*   **Project IDs:** Hardcoded to `friday-media-prod` in build YAML configurations.
*   **Bucket names:** Hardcoded to `friday-media-assets-prod` in python worker files.
*   **Firestore names:** Native `(default)`.
*   **Cloud Run Job names:** `media-pipeline`.
*   **Service names:** `media-ui`.
*   **Vertex AI region:** `us-central1`.
*   **API endpoints:** Standard GCP endpoints.
*   **Internal Consistency:** **PASS**. The hardcoded parameters are aligned to this project environment, but they block deployment to other environments.

---

## 8. END-TO-END PIPELINE VALIDATION

| Pipeline Stage | Classification | Reason for Classification |
|---|---|---|
| **Dashboard** | FAIL | Streamlit dashboard UI starts successfully but crashes with a 403 PermissionDenied error when a user attempts to submit a new generation, due to the read-only Firestore permissions on the UI service account. |
| **Trigger Job** | FAIL (NOT TESTABLE) | Cannot be triggered from the Dashboard due to the failure in the previous step. (Note: Manually triggering the job via CLI succeeds). |
| **Pipeline Coordinator** | PASS | If triggered manually, the job executes and coordinates workers successfully. |
| **Gemini API** | PASS | Vertex AI script generation succeeds, as proven by completion logs. |
| **Imagen API** | PASS | Image generation succeeds via Gemini image modality, as proven by completion logs. |
| **Text-to-Speech API**| PASS | Speech synthesis succeeds, as proven by completion logs. |
| **Storage Upload** | PASS | Successfully writes final assets to `gs://friday-media-assets-prod`. |
| **Firestore Write** | PASS | The job coordinator successfully updates document status to `published`. |
| **Dashboard Update** | PASS | Firestore status changes are readable by the dashboard once updated. |

---

## 9. DEPLOYMENT READINESS DECISION

**Should remediation proceed now?** **NO.**

**Actions required before proceeding:**
1.  **Phase 1 Approval:** Execute Phase 1 (P0) security sanitization to delete and revoke the exposed API keys and shell logs.
2.  **IAM Correction:** Bind `roles/datastore.user` to `sa-media-ui` to allow the UI service to write records to Firestore.
3.  **ActAs Binding:** Bind the `roles/iam.serviceAccountUser` role to the deploying identity.
