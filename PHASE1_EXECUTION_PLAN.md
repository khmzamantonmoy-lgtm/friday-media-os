# Phase 1 (P0) Security Sanitization Execution Plan
**Target Project:** `friday-media-os`  
**Status:** Plan Generated — Pending Approval  

This document details the exact execution steps, commands, and validation checks required to complete Phase 1 (P0) security sanitization.

---

## 1. OBJECTIVES
*   Completely remove exposed plaintext credentials (Gemini API key and YouTube API key) from the local filesystem.
*   Sanitize the terminal command logs to prevent credential leakage in shell history.
*   Ensure that no active Python, Streamlit, or rendering processes are running inside the Cloud Shell interactive environment.
*   Revoke the compromised keys at the cloud provider level.

---

## 2. PRECONDITIONS
*   Administrative access to the Google Cloud Console for the project `friday-media-os`.
*   Access to the Google AI Studio console associated with the developer's identity.
*   Active terminal session in the workspace directory `/home/khmzamantonmoy`.

---

## 3. FILES TO MODIFY
*   `/home/khmzamantonmoy/gemini_key.txt` (to be deleted)
*   `/home/khmzamantonmoy/friday-media-os-backup/.env` (to be deleted)
*   `/home/khmzamantonmoy/.bash_history` (to be deleted/cleared)

---

## 4. GCP RESOURCES AFFECTED
*   **Gemini API Key:** Associated with the user's AI Studio developer profile.
*   **YouTube API Key:** Registered under GCP APIs & Services Credentials.

---

## 5. EXACT CHANGES & CLI COMMANDS

### Command 1: Delete Local Gemini Key File
```bash
rm -f /home/khmzamantonmoy/gemini_key.txt
```
*   **Why it is required:** The file contains the active Gemini API key in plaintext. Deleting it prevents processes, users, or accidental check-ins from exposing it.
*   **What it changes:** Deletes the file `/home/khmzamantonmoy/gemini_key.txt` from the filesystem.
*   **How to verify it succeeded:** Check that the file no longer exists:
    ```bash
    ls /home/khmzamantonmoy/gemini_key.txt
    # Expected output: ls: cannot access '/home/khmzamantonmoy/gemini_key.txt': No such file or directory
    ```

### Command 2: Delete Local Backup Environment Configuration
```bash
rm -f /home/khmzamantonmoy/friday-media-os-backup/.env
```
*   **Why it is required:** The backup environment file contains the plaintext YouTube API key. Deleting it ensures no cleartext secrets remain in old project backups.
*   **What it changes:** Deletes the file `/home/khmzamantonmoy/friday-media-os-backup/.env` from the filesystem.
*   **How to verify it succeeded:** Check that the file no longer exists:
    ```bash
    ls /home/khmzamantonmoy/friday-media-os-backup/.env
    # Expected output: ls: cannot access '/home/khmzamantonmoy/friday-media-os-backup/.env': No such file or directory
    ```

### Command 3: Clear Terminal Bash History
```bash
history -c && rm -f /home/khmzamantonmoy/.bash_history
```
*   **Why it is required:** The shell history file contains cleartext recordings of export commands that contain the secret keys. Purging the file deletes the audit trail of the secrets.
*   **What it changes:** Clears the active session command buffer and deletes `/home/khmzamantonmoy/.bash_history` from the disk.
*   **How to verify it succeeded:** Check that the history file is empty or removed:
    ```bash
    cat /home/khmzamantonmoy/.bash_history
    # Expected output: cat: /home/khmzamantonmoy/.bash_history: No such file or directory
    ```

### Command 4: Check and Cease Cloud Shell Workloads
```bash
ps aux | grep -E "streamlit|python" | grep -v grep
```
*   **Why it is required:** Identifies whether any persistent python scripts or web servers are active in the interactive Cloud Shell sandbox, which would violate the Acceptable Use Policy.
*   **What it changes:** Queries the current OS process table (does not modify process state unless process IDs are returned, in which case a `kill` command must be run manually).
*   **How to verify it succeeded:** The command should return an empty output, confirming no unauthorized background processes are running:
    ```bash
    # Expected output: (Empty)
    ```

---

## 6. GCP CONSOLE ACTIONS (MANUAL REVOCATION)

Due to security boundaries, API keys cannot be programmatically deleted via the Cloud Shell CLI without administrative roles. The operator must execute the following manual revocations:

### Step 1: Revoke the Gemini API Key
1.  Navigate to the Google AI Studio console: [https://aistudio.google.com/](https://aistudio.google.com/)
2.  Click on **Get API Key** in the menu sidebar.
3.  Locate the key matching the suffix `...wAMxULPq9qUA` (or the key utilized in the project).
4.  Select the key, click the delete/trash icon, and confirm deletion.
*   **Why it is required:** Prevents any future API requests from utilizing this compromised credential.
*   **What it changes:** Deletes the key registration in Google's identity database.
*   **How to verify it succeeded:** Attempt to run a test query with the key; it should return a `400 INVALID_ARGUMENT` or `API key not valid` error.

### Step 2: Revoke the YouTube API Key
1.  Navigate to the Google Cloud Console: [https://console.cloud.google.com/](https://console.cloud.google.com/)
2.  Select the project `friday-media-os` (or the project where the key was registered).
3.  Go to **APIs & Services > Credentials**.
4.  Under **API Keys**, locate the key corresponding to `AIzaSyBqK767lUXetp4IL8klHZDXDAWG7f0ef-s`.
5.  Click the delete icon next to the key and confirm.
*   **Why it is required:** Prevents unauthorized video uploading or quota theft.
*   **What it changes:** Invalidates the API credential in GCP.
*   **How to verify it succeeded:** Attempting to query the YouTube API with the key will return an access authorization error.

---

## 7. ROLLBACK COMMANDS
*   **Filestore Rollback:**
    If the configuration file layout is needed, restore placeholder configuration templates (without the secret values):
    ```bash
    echo "PORT=8081" > /home/khmzamantonmoy/friday-media-os-backup/.env
    echo "YOUTUBE_API_KEY=PLACEHOLDER_KEY" >> /home/khmzamantonmoy/friday-media-os-backup/.env
    echo "GCP_PROJECT_ID=friday-media-os" >> /home/khmzamantonmoy/friday-media-os-backup/.env
    ```
*   **API Credentials Rollback:**
    If the systems fail to operate due to key deletion, do not reuse compromised keys. Generate a new key in the Google Cloud Console, write it as a secret inside Secret Manager, and reference it via IAM.

---

## 8. EXPECTED OUTPUTS
*   All file deletion commands exit silently with status code `0`.
*   Verification checks for `gemini_key.txt`, `.env`, and `.bash_history` return "No such file or directory."
*   Process tables are clear of Streamlit web applications and render workers.

---

## 9. SERVICE METRICS & CRITERIA

*   **Estimated Execution Time:** 10 minutes.
*   **Expected Service Interruption:** None (no components are running or serving traffic in the current project state).
*   **Success Criteria:**
    - [ ] Both target files are deleted.
    - [ ] Bash history is cleared.
    - [ ] Local process table contains no Streamlit or FFmpeg worker processes.
    - [ ] Compromised keys return authentication failures when tested.
*   **Failure Criteria:**
    - [ ] Deletion commands exit with error code (except if files were already removed).
    - [ ] Key verification command reveals the files still exist.
    - [ ] Old credential keys remain valid and active on GCP or AI Studio.
