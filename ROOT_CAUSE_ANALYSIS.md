# Root Cause Analysis (RCA) — Firestore Write Failure
**Target Project:** `friday-media-prod`  
**Current Account:** `khmzamantonmoy@gmail.com`  
**Current Region:** `us-central1`  
**Status:** RCA Completed — Awaiting Approval  

This report identifies the root cause of the `PermissionDenied` error encountered by the UI Cloud Run service when attempting to write to the Firestore database.

---

## 1. ACTIVE CLOUD RUN REVISION
*   **Service Name:** `media-ui`
*   **Active Revision:** `media-ui-00004-f6d`
*   **Image Digest:** `us-central1-docker.pkg.dev/friday-media-prod/media-pipeline/ui@sha256:494699344ab5151470fc2551e88c28a073e6924c39b102cd3564d1f874bdfd6c`
*   **Service Account:** `sa-media-ui@friday-media-prod.iam.gserviceaccount.com`
*   **Environment Variables:**
    *   `GCP_PROJECT_ID` = `"friday-media-prod"`
    *   `GCP_REGION` = `"us-central1"`
    *   `PIPELINE_JOB_NAME` = `"media-pipeline"`

---

## 2. CALLING IDENTITY DETAILS
*   **Service Account Email:** `sa-media-ui@friday-media-prod.iam.gserviceaccount.com`
*   **Workload / Credentials Source:** The container retrieves OAuth 2.0 access tokens from the default Cloud Run metadata server endpoint (`http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token`).
*   **Authenticated Principal:** `sa-media-ui@friday-media-prod.iam.gserviceaccount.com`

---

## 3. DENIED PERMISSION SPECIFICS
*   **Failing API:** `firestore.googleapis.com` (Google Cloud Firestore API)
*   **Failing Operation:** Batch write commit initiated during the execution of `.set()` in `/app/src/config/firestore_schema.py` line 104:
    ```python
    db.collection("content_items").document(content_id).set({...})
    ```
*   **Resource Accessed:** A document located under `projects/friday-media-prod/databases/(default)/documents/content_items/[content_id]`.
*   **Failing IAM Permission:** "There is insufficient evidence to determine the denied IAM permission." (The gRPC error payload from the Firestore service only returns `PermissionDenied: 403 Missing or insufficient permissions.` without identifying the specific permission string).

---

## 4. IDENTITY PERMISSION MATRIX
The following matrix compares the IAM roles assigned to the **UI Service Account** (`sa-media-ui`) vs. the **Pipeline Service Account** (`sa-media-pipeline`).

| Resource / API | UI Service Account (`sa-media-ui`) | Pipeline Service Account (`sa-media-pipeline`) | Difference / Highlight |
|---|---|---|---|
| **Firestore** | `roles/datastore.viewer` | `roles/datastore.user` | **UI SA has read-only access.** Pipeline SA has read-write access. |
| **Storage** | None | `roles/storage.objectAdmin` | **UI SA has no access.** Pipeline SA has project-level write access. |
| **Vertex AI** | None | `roles/aiplatform.user` | **UI SA has no access.** Pipeline SA has model query access. |
| **Cloud Run** | `roles/run.developer` | None | **UI SA has deployment control.** Pipeline SA has no access. |
| **Artifact Registry** | None | None | No difference. |
| **Logging** | None | None | No difference. |

---

## 5. UI WRITE LEGITIMACY & MINIMUM PERMISSION
*   **Legitimacy:** **YES**. The Streamlit dashboard UI must write to Firestore. When a user clicks "Generate Content", the application executes `create_content_item(db, content_id, brand_id, topic)` to record a metadata draft before triggering the Cloud Run Job. Without this write capability, the pipeline trigger sequence cannot initiate.
*   **Minimum Predefined Role Required:** `roles/datastore.user` (Grants read/write permissions for Cloud Firestore databases and entities).
*   **Fine-grained Permissions Required:**
    *   `datastore.entities.create`
    *   `datastore.entities.update`
    *   `datastore.entities.get`
    *   `datastore.entities.list`

---

## 6. FIRESTORE SECURITY RULES VALIDATION
*   **Security Rules Status:** Firestore Security Rules are **not responsible** for this failure.
    *   *Evidence:* The application uses the server-side Python library `google-cloud-firestore` which interacts with Firestore using service credentials via the gRPC Admin API. Firebase Security Rules are bypassed for server-side admin SDK calls and are only enforced on client-side requests (web/mobile SDKs). The authorization boundary is governed entirely by project-level GCP IAM policies.

---

## 7. ROOT CAUSE SUMMARY
The root cause is an **IAM configuration error**. The service account associated with the UI container (`sa-media-ui`) is only granted `roles/datastore.viewer`, which permits data reading but denies write operations. Because `Home.py` executes a Firestore write operation (`create_content_item`), the request is rejected with a `403 PermissionDenied` error. In contrast, the Pipeline Job runs under the `sa-media-pipeline` identity, which is correctly granted `roles/datastore.user` (read-write), allowing it to successfully write task updates to the database.
