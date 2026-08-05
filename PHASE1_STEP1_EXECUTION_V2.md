# Phase 1 Step 1 IAM Adjustment Execution Plan (Version 2)
**Target Project:** `friday-media-prod`  
**Current Account:** `khmzamantonmoy@gmail.com`  
**Current Region:** `us-central1`  
**Status:** Step Plan V2 Created — Awaiting Approval  

This document outlines the zero-downtime, additive-first execution plan for modifying permissions on the `sa-media-ui` service account to resolve Firestore write failures.

---

## 1. PRECONDITIONS
*   Administrative access permissions to bind and remove project-level IAM roles in the `friday-media-prod` project.
*   Authenticated gcloud terminal session targeting the active project `friday-media-prod`.
*   The target service account `sa-media-ui@friday-media-prod.iam.gserviceaccount.com` exists.

---

## 2. ADDITIVE GCLOUD EXECUTION
To implement the additive-first change, execute the following command:

```bash
# Grant datastore.user (read-write) to the service account
gcloud projects add-iam-policy-binding friday-media-prod \
  --member="serviceAccount:sa-media-ui@friday-media-prod.iam.gserviceaccount.com" \
  --role="roles/datastore.user"
```
*   *Note: Do NOT execute any remove command for roles/datastore.viewer during this step. The existing viewer binding must remain in place to guarantee zero runtime disruption.*

---

## 3. EXPECTED IAM POLICY DIFF
Applying the additive command will result in the following project IAM policy modifications:

```diff
 bindings:
   - members:
     - serviceAccount:sa-media-ui@friday-media-prod.iam.gserviceaccount.com
     role: roles/run.developer
   - members:
     - serviceAccount:sa-media-ui@friday-media-prod.iam.gserviceaccount.com
     role: roles/datastore.viewer
+  - members:
+    - serviceAccount:sa-media-ui@friday-media-prod.iam.gserviceaccount.com
+    role: roles/datastore.user
```

---

## 4. VERIFICATION GATE
Immediately after granting the role, perform the following validation checks. **Do not proceed if any check fails.**

1.  **IAM Policy Verification:**
    Confirm both `datastore.viewer` and `datastore.user` bindings exist for the service account:
    ```bash
    gcloud projects get-iam-policy friday-media-prod \
      --flatten="bindings[].members" \
      --filter="bindings.members:sa-media-ui@friday-media-prod.iam.gserviceaccount.com" \
      --format="table(bindings.role)"
    ```
    *   *Expected output:*
        ```
        ROLE
        roles/datastore.user
        roles/datastore.viewer
        roles/run.developer
        ```

2.  **Service Health Verification:**
    Check that the Cloud Run UI service remains in a Ready status:
    ```bash
    gcloud run services describe media-ui --region=us-central1 --format="value(status.conditions[0].status)"
    ```
    *   *Expected output:* `True`

3.  **UI Verification:**
    Open the dashboard URL in a browser: `https://media-ui-ylzb4xvega-uc.a.run.app` and check that the home page loads successfully.

4.  **Firestore Write Verification:**
    Submit a new content generation request using the UI form. Check that the submission succeeds on screen.

5.  **Document Verification:**
    Verify a new document matching the generated topic and ID appears in the Firestore `content_items` collection:
    ```bash
    # Run query to list the 3 most recent content items
    python3 -c "
    from google.cloud import firestore
    db = firestore.Client(project='friday-media-prod')
    for doc in db.collection('content_items').order_by('created_at', direction=firestore.Query.DESCENDING).limit(3).stream():
        print(doc.id, doc.to_dict().get('topic'), doc.to_dict().get('status'))
    "
    ```

6.  **Container Error Verification:**
    Verify no new `PermissionDenied` errors are written to the UI service container logs:
    ```bash
    gcloud logging read "resource.type=\"cloud_run_revision\" AND resource.labels.service_name=\"media-ui\" AND textPayload:PermissionDenied" --project=friday-media-prod --limit=5
    ```
    *   *Expected output:* (No new timestamps matching the post-remediation timeframe).

7.  **Cloud Run Job Verification:**
    Verify the triggered Cloud Run Job executes successfully:
    ```bash
    gcloud run jobs list --project=friday-media-prod
    # Followed by checking the execution status of the job run triggered by the write
    gcloud run jobs executions list --job=media-pipeline --region=us-central1 --limit=1
    ```
    *   *Expected completion status:* `EXECUTION_SUCCEEDED`

8.  **Job Pipeline Storage & Firestore verification:**
    Verify that the job coordinator successfully writes the `published` status to Firestore and uploads media files (audio, frames, and video render) to `gs://friday-media-assets-prod`.
    ```bash
    gsutil ls -r gs://friday-media-assets-prod/
    ```

9.  **Dashboard Status Update:**
    Refresh the Streamlit dashboard home page and confirm that the status of the new item has transitioned from `DRAFT` / `RENDERING` to `PUBLISHED`.

---

## 5. ROLLBACK STRATEGY
If any verification check in the Verification Gate fails, execute this rollback command immediately:

```bash
# Remove only the newly added datastore.user binding
gcloud projects remove-iam-policy-binding friday-media-prod \
  --member="serviceAccount:sa-media-ui@friday-media-prod.iam.gserviceaccount.com" \
  --role="roles/datastore.user"
```
*   *Note: Do not touch, alter, or remove the pre-existing roles/datastore.viewer or roles/run.developer bindings. This returns the environment to its exact pre-remediation state safely.*

---

## 6. POST-VALIDATION CLEANUP (OPTIONAL)
Only after completing the Verification Gate successfully, the following cleanup command is recommended to remove the redundant read-only role:

```bash
# Optional cleanup of superseded viewer role
gcloud projects remove-iam-policy-binding friday-media-prod \
  --member="serviceAccount:sa-media-ui@friday-media-prod.iam.gserviceaccount.com" \
  --role="roles/datastore.viewer"
```

---

## 7. RISK ASSESSMENT
*   **Blast Radius:** Isolated to the `sa-media-ui` service account permissions. The additive policy binding does not affect project billing, the running `media-pipeline` Cloud Run Job, or other system accounts.
*   **Downtime Expected:** **Zero.** Additive policy bindings do not restart or interrupt running Cloud Run containers. The current active container revision remains live and active throughout the process.
*   **Recovery Time:** Under 1 minute (to execute the rollback command).
*   **Rollback Time:** Under 1 minute.
*   **Operational Impact:** None. The addition of write permissions is backwards-compatible and only enables functionality that was previously blocked.

---

## 8. SUCCESS CRITERIA
The remediation is considered successful only if:
1.  The UI dashboard can successfully write and create draft documents in Firestore.
2.  No `PermissionDenied` errors are generated in the `media-ui` container stderr stream.
3.  Existing pipeline behaviors (manual job triggering and rendering) are unchanged.
4.  Existing Cloud Run Job capabilities remain fully operational.
5.  GCS media writes and updates continue to succeed.
