# Minimum Fix Plan — Firestore Permission Issue
**Target Project:** `friday-media-prod`  
**Current Account:** `khmzamantonmoy@gmail.com`  
**Current Region:** `us-central1`  
**Status:** Fix Plan Created — Awaiting Approval  

This plan outlines the minimum operational changes required to resolve the Firestore PermissionDenied error for the `media-ui` service.

---

## 1. ROLE CHANGES
*   **Target Service Account:** `sa-media-ui@friday-media-prod.iam.gserviceaccount.com`
*   **Role to Add:** `roles/datastore.user` (Predefined role for Firestore read-write access).
*   **Role to Remove:** `roles/datastore.viewer` (Read-only role, now redundant).

---

## 2. SERVICE ACCOUNT CHANGES
*   **No service accounts will be created or deleted.** The fix relies entirely on modifying permissions for the existing `sa-media-ui@friday-media-prod.iam.gserviceaccount.com` service account.

---

## 3. FILE MODIFICATIONS
*   **No file modifications are required.** The application code in `Home.py` and `firestore_schema.py` is structurally correct. The issue is an external IAM policy constraint.

---

## 4. EXACT CLI COMMANDS
To apply the required role changes, execute:

```bash
# 1. Add read-write role to the UI service account
gcloud projects add-iam-policy-binding friday-media-prod \
  --member="serviceAccount:sa-media-ui@friday-media-prod.iam.gserviceaccount.com" \
  --role="roles/datastore.user"

# 2. Remove the redundant read-only role
gcloud projects remove-iam-policy-binding friday-media-prod \
  --member="serviceAccount:sa-media-ui@friday-media-prod.iam.gserviceaccount.com" \
  --role="roles/datastore.viewer"
```

---

## 5. ROLLBACK COMMANDS
To revert the changes in the event of an operational failure, execute:

```bash
# 1. Restore the read-only role
gcloud projects add-iam-policy-binding friday-media-prod \
  --member="serviceAccount:sa-media-ui@friday-media-prod.iam.gserviceaccount.com" \
  --role="roles/datastore.viewer"

# 2. Remove the read-write role
gcloud projects remove-iam-policy-binding friday-media-prod \
  --member="serviceAccount:sa-media-ui@friday-media-prod.iam.gserviceaccount.com" \
  --role="roles/datastore.user"
```

---

## 6. VERIFICATION COMMANDS
To verify that the IAM changes were successfully applied to the service account, execute:

```bash
# Query the project's IAM policy for sa-media-ui bindings
gcloud projects get-iam-policy friday-media-prod \
  --flatten="bindings[].members" \
  --filter="bindings.members:sa-media-ui@friday-media-prod.iam.gserviceaccount.com" \
  --format="table(bindings.role)"
```

*   **Expected Output:**
    ```
    ROLE
    roles/datastore.user
    roles/run.developer
    ```

---

## 7. EXPECTED OUTCOME
Following implementation, the UI service container will possess the required permissions (`datastore.entities.create` and `datastore.entities.update`) to perform writes. When a user submits the dashboard generation form, the metadata draft will be successfully created in Firestore and the backend Cloud Run Job will trigger, resolving the runtime failure.
