# Change Advisory Board (CAB) Audit Review
**Target Document:** `REMEDIATION_PRIORITY.md`  
**Review Type:** Consistency, Dependency, and Safety Validation  
**Status:** Review Completed — Pending Approval  

This report provides the Change Advisory Board (CAB) evaluation of the prioritized remediation roadmap. No commands have been executed and no code files have been modified.

---

## CAB VALIDATION OVERVIEW

We evaluated the proposed roadmap against the core requirements of security, reliability, operational excellence, and deployment continuity. The target environment is currently empty of compute resources, which simplifies the migration path. However, several critical dependency gaps, configuration conflicts, and security assumptions must be addressed before execution.

---

## CLASSIFIED FINDINGS

### 1. Missing IAM ActAs Privilege for Cloud Run Deployments
*   **Classification:** High
*   **Issue Type:** Missing prerequisites
*   **Details:** Phase 4 executes `deploy.sh`, which deploys the UI Service (`media-ui`) and the Pipeline Job (`media-pipeline`) under their respective service accounts (`sa-media-ui` and `sa-media-pipeline`). However, the deployer identity (either the developer's personal account or the Cloud Build runner) requires the `roles/iam.serviceAccountUser` role (permitting `iam.serviceAccounts.actAs`) on both service accounts. Without this, the deployment will fail immediately with permission denied errors.
*   **Opportunity to Reduce Risk:** Add IAM binding steps in Phase 2 to explicitly grant `roles/iam.serviceAccountUser` on the created service accounts to the deploying identity.

---

### 2. Inaccessibility Risk due to Cloud Run Private Invocations
*   **Classification:** High
*   **Issue Type:** Unsafe assumptions / Operational risks
*   **Details:** Phase 4 deploys the Streamlit UI dashboard with the `--no-allow-unauthenticated` flag. Streamlit has no built-in user authentication. Restricting invoker access directly at the Cloud Run service level will make the dashboard URL return a `403 Forbidden` error to all standard web browsers, breaking user access.
*   **Opportunity to Reduce Risk:** Keep the service private but define a clear path to access it:
    1.  Enforce user sign-in using IAP (Identity-Aware Proxy), which requires configuring an external HTTP(S) Load Balancer.
    2.  Promote IAP and Load Balancer configurations from "Optional Hardening" to a required prerequisite in Phase 2/3.
    3.  Alternatively, implement basic authorization middleware directly within the Streamlit codebase.

---

### 3. Inconsistency in Billing Budget Deployment Scheduling
*   **Classification:** Medium
*   **Issue Type:** Circular dependencies / Phase ordering
*   **Details:** The budget policy creation command is bundled within `setup_gcp_safe.sh` (executed in Phase 2). However, Finding 7 (Billing Budgets) lists its implementation target as Phase 5. This results in a phase-ordering conflict where the budget is technically deployed in Phase 2, making the Phase 5 timeline redundant.
*   **Opportunity to Reduce Risk:** Align the roadmap schedule. Move the budget alert configuration description to Phase 2 in the roadmap, or isolate the budget creation logic from `setup_gcp_safe.sh` to run separately in Phase 5.

---

### 4. Incomplete Verification for Project-Level GCS Role Removal
*   **Classification:** Low
*   **Issue Type:** Missing verification steps
*   **Details:** For Finding 6 (Project-Wide GCS Permissions), the verification command only checks the bucket-level IAM policy:
    `gcloud storage buckets get-iam-policy gs://friday-media-assets-friday-media-os`
    It fails to verify whether the broad project-wide `roles/storage.objectAdmin` binding was successfully removed from the service account.
*   **Opportunity to Reduce Risk:** Append a project-level IAM check to the verification step:
    ```bash
    gcloud projects get-iam-policy friday-media-os --format=json | grep -A2 "sa-media-pipeline"
    ```

---

### 5. Absence of Credentials Deletion Rollback Protocol
*   **Classification:** Medium
*   **Issue Type:** Missing rollback steps
*   **Details:** Finding 1 (Exposed Credentials) lists the rollback command as "N/A." If the keys are revoked and deleted, but a legacy or external process depends on them, the system will break without a recovery path. While keys cannot be un-revoked, a remediation playbook should be defined.
*   **Opportunity to Reduce Risk:** Provide a clear rollback process:
    1.  Generate a temporary replacement key in Google AI Studio or GCP console.
    2.  Securely inject the new key into the failing client application config.

---

### 6. Validation of Downtime Assumptions
*   **Classification:** Low
*   **Issue Type:** Unsafe assumptions
*   **Details:** The roadmap assumes "None" downtime for all phases. This is technically true because the project currently has no active users or deployed compute resources. However, if this migration pattern were executed on an active system, deploying the Cloud Run UI with private invocation parameters would introduce downtime. This context should be explicitly documented in the roadmap assumptions.

---

## CAB ACTION ITEM SUMMARY

| Phase | Action Item / Correction Required | Classification |
|---|---|---|
| **Phase 2** | Add `iam.serviceAccounts.actAs` role bindings to the deployer identity. | High |
| **Phase 2** | Resolve phase-ordering conflict: clarify whether `setup_gcp_safe.sh` runs the budget creation or if it is deferred to Phase 5. | Medium |
| **Phase 3** | Append project-level IAM policy checks to the storage permission verification step. | Low |
| **Phase 4** | Define access architecture (e.g., IAP/Load Balancer or Streamlit auth proxy) for private Cloud Run UI to prevent user lock-out. | High |
| **Phase 1-5**| Document that the "No Downtime" assumption is valid only because there are currently zero deployed compute resources. | Low |
