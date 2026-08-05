# UI Service Runtime Evidence Report
**Target Project:** `friday-media-prod`  
**Current Account:** `khmzamantonmoy@gmail.com`  
**Current Region:** `us-central1`  
**Status:** Runtime Evidence Collected — Awaiting Approval  

This document contains actual log and configuration evidence collected from the active `friday-media-prod` project. No configurations have been modified.

---

## 1. CURRENT CLOUD RUN REVISION: `media-ui-00004-f6d`
*   **Revision name:** `media-ui-00004-f6d`
*   **Image digest:** `us-central1-docker.pkg.dev/friday-media-prod/media-pipeline/ui@sha256:494699344ab5151470fc2551e88c28a073e6924c39b102cd3564d1f874bdfd6c`
*   **Image tag:** `latest` (resolved at deployment time to the digest above)
*   **Service account:** `sa-media-ui@friday-media-prod.iam.gserviceaccount.com`
*   **CPU:** `1000m` (1 CPU)
*   **Memory:** `1Gi`
*   **Concurrency:** `80`
*   **Environment variables:**
    *   `GCP_PROJECT_ID` = `"friday-media-prod"`
    *   `GCP_REGION` = `"us-central1"`
    *   `PIPELINE_JOB_NAME` = `"media-pipeline"`
*   **Ingress:** `all` (all traffic allowed)
*   **Authentication:** Public access allowed (`allUsers` bound to `roles/run.invoker`).

---

## 2. RUNTIME STARTUP VERIFICATION
The container booted successfully, as proven by the following startup logs:
```
2026-08-02T03:56:39.439603Z	  You can now view your Streamlit app in your browser.
2026-08-02T03:56:39.439740Z	  URL: http://0.0.0.0:8501
```

---

## 3. RUNTIME FAILURE
The latest failed UI request recorded on `2026-08-02T04:00:52.887195402Z` generated the following error log:

```
Traceback (most recent call last):
  File "/usr/local/lib/python3.11/site-packages/streamlit/runtime/scriptrunner/exec_code.py", line 88, in exec_func_with_error_handling
    result = func()
             ^^^^^^
  File "/usr/local/lib/python3.11/site-packages/streamlit/runtime/scriptrunner/script_runner.py", line 590, in code_to_exec
    exec(code, module.__dict__)
  File "/app/dashboard/Home.py", line 63, in <module>
    create_content_item(db, content_id, brand_id, topic)
  File "/app/src/config/firestore_schema.py", line 104, in create_content_item
    db.collection("content_items").document(content_id).set({
  File "/usr/local/lib/python3.11/site-packages/google/cloud/firestore_v1/document.py", line 166, in set
    write_results = batch.commit(**kwargs)
                    ^^^^^^^^^^^^^^^^^^^^^^
  File "/usr/local/lib/python3.11/site-packages/google/cloud/firestore_v1/batch.py", line 59, in commit
    commit_response = self._client._firestore_api.commit(
                      ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/usr/local/lib/python3.11/site-packages/google/cloud/firestore_v1/services/firestore/client.py", line 1372, in commit
    response = rpc(
               ^^^^
  File "/usr/local/lib/python3.11/site-packages/google/api_core/gapic_v1/method.py", line 128, in __call__
    return wrapped_func(*args, **kwargs)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/usr/local/lib/python3.11/site-packages/google/api_core/grpc_helpers.py", line 57, in error_remapped_callable
    raise exceptions.from_grpc_error(exc) from exc
google.api_core.exceptions.PermissionDenied: 403 Missing or insufficient permissions.
```

*   **Complete stack trace:** (Quoted above).
*   **Full PermissionDenied message:** `google.api_core.exceptions.PermissionDenied: 403 Missing or insufficient permissions.`
*   **RPC error:** Mapped from `grpc._InactiveRpcError` representing `StatusCode.PERMISSION_DENIED`.
*   **Failing API:** Google Cloud Firestore API (`firestore.googleapis.com`).
*   **Failing Firestore operation:** `set` (batch write commit).
*   **Resource being accessed:** A document under the `content_items` collection: `db.collection("content_items").document(content_id)`.

---

## 4. FIRESTORE IDENTITY VERIFICATION
*   **Attempted Identity:** The request was executed by the active revision running under the service account `sa-media-ui@friday-media-prod.iam.gserviceaccount.com`.
*   **Denied IAM Permission:** "There is insufficient evidence to identify the denied IAM permission." (The gRPC error payload from the Firestore service only returns `Missing or insufficient permissions` without identifying the exact permission string).

---

## 5. STORAGE BUCKET VERIFICATION
Based on project and bucket-level IAM configurations:
*   **UI Service Account Read Capability:** **NO**. The project IAM policy has no storage roles bound to `sa-media-ui@friday-media-prod.iam.gserviceaccount.com`, and the bucket IAM policy for `gs://friday-media-assets-prod` contains no references to this account.
*   **UI Service Account Write Capability:** **NO**. The project IAM policy has no storage roles bound to `sa-media-ui@friday-media-prod.iam.gserviceaccount.com`, and the bucket IAM policy for `gs://friday-media-assets-prod` contains no references to this account.

---

## 6. DEPLOYMENT VERIFICATION
*   **Latest Image in Artifact Registry:** `us-central1-docker.pkg.dev/friday-media-prod/media-pipeline/ui@sha256:47bd45aa9e4f0734e909a4ce1f14f82662b9fe0c9f6a8bfed4efc384fa690010` (Created `2026-08-02T05:56:02`).
*   **Deployed Revision Image:** `us-central1-docker.pkg.dev/friday-media-prod/media-pipeline/ui@sha256:494699344ab5151470fc2551e88c28a073e6924c39b102cd3564d1f874bdfd6c` (Created `2026-08-02T05:55:53`).
*   **Matching Status:** **MISMATCH**. The deployed revision `media-ui-00004-f6d` runs an older image and does not match the latest Artifact Registry image digest.

---

## 7. FINAL ASSESSMENT
*   **UI Failure Cause:** **IAM**.
    *   *Evidence:* The UI Service Account `sa-media-ui@friday-media-prod.iam.gserviceaccount.com` is granted `roles/datastore.viewer` in the project IAM bindings. The `roles/datastore.viewer` role is read-only and does not permit document writing (`set` operations). The application code in `Home.py` executes a Firestore write operation (`create_content_item`), which triggers the `PermissionDenied` error.
