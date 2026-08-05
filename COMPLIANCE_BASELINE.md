# Production Compliance Baseline
**Project ID:** `friday-media-os`  
**Status:** Baseline Reference Document  

This document defines the target state for a production-ready Google Cloud environment for the Media OS application. The configurations and standards below are designed to adhere to the Google Cloud Architecture Framework, focusing on security, reliability, operational excellence, and cost optimization.

---

## 1. Current Project Posture
As of the latest audit, the project has been reinstated but remains in a bare state without production-grade controls:
*   **Compute:** No active Cloud Run services or jobs are currently deployed.
*   **Identity & Access Management:** No granular, least-privilege service accounts exist. Default compute service accounts are currently active but unassigned to specific roles.
*   **Storage & Database:** The default Firestore database exists in native mode with delete protection disabled. A single Cloud Storage bucket exists with uniform bucket-level access enabled, but without scoped role bindings.
*   **APIs:** Necessary APIs (Vertex AI, Cloud Run, Storage, Firestore) are enabled, alongside newly enabled helper APIs (Cloud Build, Billing Budgets).
*   **Secrets:** Plaintext API credentials have been exposed in environment variables, configuration backups, and interactive terminal histories.

---

## 2. Required Remediation
Before deploying any compute resources, the following remediation steps must be performed to address security issues and compliance gaps:
1.  **Revocation of Compromised Credentials:**
    *   Revoke the exposed Gemini API key in the Google AI Studio console.
    *   Revoke the exposed YouTube API key in the GCP Credentials dashboard.
2.  **Removal of Local Plaintext Secrets:**
    *   Delete the plaintext key file `/home/khmzamantonmoy/gemini_key.txt`.
    *   Delete `/home/khmzamantonmoy/friday-media-os-backup/.env` to eliminate plaintext backups of credentials.
3.  **Sanitization of Terminal Logs:**
    *   Clear the local bash command history to ensure no exposed credentials remain in plaintext logs.
4.  **Refactoring Environment Configuration:**
    *   Remove hardcoded GCS bucket name strings (`friday-media-assets-prod`) from active Python workers (`voice_worker.py`, `image_worker.py`, `render_worker.py`).
    *   Configure worker modules to dynamically retrieve the GCS bucket name using environment variables or credentials metadata.

---

## 3. Optional Hardening
For projects requiring advanced security perimeters, implement the following security layers:
*   **Identity-Aware Proxy (IAP):** Place the front-end dashboard behind IAP to enforce identity-based access control (OIDC/OAuth 2.0) before requests reach the Cloud Run UI service.
*   **VPC Service Controls (VPC-SC):** Place Firestore, Cloud Storage, and Vertex AI inside a VPC Service Controls perimeter to mitigate the risk of data exfiltration.
*   **Customer-Managed Encryption Keys (CMEK):** Use Cloud Key Management Service (KMS) to encrypt Firestore databases and GCS storage buckets with customer-managed keys.

---

## 4. Least-Privilege IAM Matrix
Do not use default service accounts or grant project-level administrative permissions. Deployed components must run under dedicated, identities scoped to specific resources.

| Component / Identity | Recommended Service Account | GCP Roles | Scoping / Resource Constraint |
|---|---|---|---|
| **Streamlit UI Service** | `sa-media-ui@friday-media-os.iam.gserviceaccount.com` | `roles/datastore.viewer`<br>`roles/run.developer` | Restricted to Firestore read-only access.<br>Scoped strictly to trigger the `media-pipeline` Cloud Run Job. |
| **Pipeline Worker Job** | `sa-media-pipeline@friday-media-os.iam.gserviceaccount.com` | `roles/datastore.user`<br>`roles/aiplatform.user`<br>`roles/storage.objectAdmin` | Firestore read/write access.<br>Vertex AI API access.<br>Bound strictly at the bucket level for `gs://friday-media-assets-friday-media-os`. |

---

## 5. Secret Management Strategy
*   **Zero-Plaintext Policy:** Plaintext secrets must never be committed to source code repositories, saved in build configurations, or set as static container environment variables.
*   **Secret Manager Integration:** All third-party secrets (e.g., YouTube API tokens, social media credentials) must be stored in Google Cloud Secret Manager.
*   **IAM Scoping:** Access to secrets must be granted explicitly to the service account of the component requiring them using the Secret Manager Secret Accessor role (`roles/secretmanager.secretAccessor`) on the specific secret resource.

---

## 6. Cloud Run Deployment Standards
*   **Deployment Architecture:** Segregate request-driven components from batch processing engines.
    *   **UI Dashboard:** Deployed as a Cloud Run **Service** configured to scale to zero (`--min-instances=0`) when idle to minimize costs.
    *   **Generation Engine:** Deployed as a Cloud Run **Job** that executes tasks to completion and exits, ensuring no persistent listening processes remain.
*   **Access Control:** Do not deploy internal or admin interfaces with public, unauthenticated invoker permissions. Remove the `--allow-unauthenticated` flag for any non-public endpoints.
*   **Resource Bounds:** Configure explicit memory and CPU limits on containers to prevent compute resource starvation or unexpected billing overruns.

---

## 7. Cloud Build Standards
*   **Immutable Configuration:** Build scripts must utilize built-in substitution variables (such as `$PROJECT_ID` and `$LOCATION`) instead of hardcoded project namespaces.
*   **Isolated Build Service Accounts:** Execute builds using a user-specified service account possessing minimal required privileges (`roles/artifactregistry.writer`, `roles/logging.logWriter`) rather than the default over-privileged Cloud Build service account.

---

## 8. Artifact Registry Standards
*   **Repository Isolation:** Maintain a dedicated Artifact Registry repository (e.g., `media-pipeline`) for the project.
*   **Vulnerability Scanning:** Enable automatic container vulnerability scanning on the repository to detect software vulnerabilities in container base images.
*   **Clean-up Policies:** Configure repository lifecycle policies to automatically delete old tags and unused container images, mitigating storage cost creep.

---

## 9. Logging and Monitoring Standards
*   **Data Access Audit Logs:** Enable Data Access audit logs for Cloud Storage and Cloud Firestore to maintain a complete history of read and write interactions.
*   **Monitoring Alerts:** Configure monitoring alert policies to notify administrators of:
    *   Elevated container crash loops or service restarts.
    *   Abnormal spikes in CPU or memory consumption.
    *   API quota usage approaching warning thresholds (80%+).

---

## 10. Cost Controls
*   **Dedicated Budgets:** Configure a project-specific billing budget linked to the billing account.
*   **Threshold Alerts:** Set up automated email alerts at 50%, 90%, and 100% of the budgeted threshold (e.g., $20/month).
*   **Automated Cost Shutdown (Pub/Sub):** Link budget alerts to a Pub/Sub topic and a Cloud Function to automatically disable billing or suspend compute resources if the budget threshold is fully exhausted.

---

## 11. Operational Compliance Checklist

- [ ] All plaintext credentials have been revoked and deleted from the local directory and shell logs.
- [ ] Granular service accounts (`sa-media-ui`, `sa-media-pipeline`) have been created with least-privilege roles.
- [ ] GCS bucket role bindings are applied at the bucket level rather than project-wide.
- [ ] GCS bucket name resolution in source code is dynamic, using runtime environment credentials.
- [ ] Firestore database delete protection is enabled.
- [ ] Cloud Run Service is deployed with scaling boundaries (`min-instances=0`, `max-instances=2`).
- [ ] Pipeline workloads are migrated entirely to Cloud Run Jobs (running to completion and exiting).
- [ ] Billing budget and alerts are configured.
- [ ] Security Command Center is monitored for vulnerability findings.
