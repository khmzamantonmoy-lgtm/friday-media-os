# Phase 1 Step 1 IAM Adjustment Execution Plan
**Target Project:** `friday-media-prod`  
**Current Account:** `khmzamantonmoy@gmail.com`  
**Current Region:** `us-central1`  
**Status:** Step Plan Created — Awaiting Approval  

This document outlines the execution plan for modifying permissions on the `sa-media-ui` service account to resolve the Firestore write failures.

---

## 1. PRECONDITIONS
*   Administrative access permissions to bind and remove project-level IAM roles in the `friday-media-prod` project.
*   Authenticated gcloud terminal session targeting the active project `friday-media-prod`.
*   The target service account `sa-media-ui@friday-media-prod.iam.gserviceaccount.com` exists.

---

## 2. EXACT GCLOUD COMMANDS
To execute the IAM role adjustment, run the following two commands:

```bash
# 1. Bind the read-write Firestore role to the UI service account
gcloud projects add-iam-policy-binding friday-media-prod \
  --member="serviceAccount:sa-media-ui@friday-media-prod.iam.gserviceaccount.com" \
  --role="roles/datastore.user"

# 2. Remove the redundant read-only role
gcloud projects remove-iam-policy-binding friday-media-prod \
  --member="serviceAccount:sa-media-ui@friday-media-prod.iam.gserviceaccount.com" \
  --role="roles/datastore.viewer"
```

---

## 3. EXPECTED IAM POLICY DIFF
Applying the commands will result in the following project IAM policy modifications:

```diff
 bindings:
+- members:
+  - serviceAccount:sa-media-ui@friday-media-prod.iam.gserviceaccount.com
+  role: roles/datastore.user
- - members:
-   - serviceAccount:sa-media-ui@friday-media-prod.iam.gserviceaccount.com
-   role: roles/datastore.viewer
```

---

## 4. VERIFICATION COMMANDS
To verify that the permissions were modified successfully, execute:

```bash
gcloud projects get-iam-policy friday-media-prod \
  --flatten="bindings[].members" \
  --filter="bindings.members:sa-media-ui@friday-media-prod.iam.gserviceaccount.com" \
  --format="table(bindings.role)"
```

*   **Expected CLI Output:**
    ```
    ROLE
    roles/datastore.user
    roles/run.developer
    ```

---

## 5. ROLLBACK COMMANDS
To revert the changes in the event of an operational failure, execute:

```bash
# 1. Re-bind the read-only Firestore role
gcloud projects add-iam-policy-binding friday-media-prod \
  --member="serviceAccount:sa-media-ui@friday-media-prod.iam.gserviceaccount.com" \
  --role="roles/datastore.viewer"

# 2. Remove the read-write Firestore role
gcloud projects remove-iam-policy-binding friday-media-prod \
  --member="serviceAccount:sa-media-ui@friday-media-prod.iam.gserviceaccount.com" \
  --role="roles/datastore.user"
```

---

## 6. SUCCESS CRITERIA
*   Both gcloud commands return successfully with status code `0`.
*   The verification command returns exactly `roles/datastore.user` and `roles/run.developer` as the active bindings for `sa-media-ui`.
*   The Streamlit UI no longer logs `403 PermissionDenied` errors when creating content drafts, and the UI status dashboard successfully records generated content items.

---

## 7. FAILURE CRITERIA
*   The gcloud commands exit with an error code (e.g., `403 Forbidden` due to caller's insufficient project access).
*   The verification output still lists `roles/datastore.viewer`.
*   The UI container standard error logs continue to record `PermissionDenied` tracebacks during database writes.
