# FRIDAY Media OS — System Architecture

## Architectural Philosophy
Decoupled, event-driven, and serverless. The system separates the **Oversight Layer** (Dashboard) from the **Execution Layer** (Workers) to ensure scalability and GCP compliance.

## Components

### 1. Executive Oversight Console (Streamlit)
*   **Role**: Real-time monitoring and global command toggles.
*   **Compute**: Cloud Run Service (lightweight, interactive).
*   **Data**: Firestore (Real-time snapshots).

### 2. Editorial AI Brains (Gemini 2.5 Flash)
*   **Role**: Autonomous decision-making, scriptwriting, and metadata generation.
*   **Logic**: Specialization via rigid System Instructions.
*   **Context**: 30-item Topic Memory to prevent content duplication.

### 3. Production Pipeline (Cloud Run Jobs)
*   **Trigger**: Autonomous Scheduler or Dashboard Override.
*   **Stages**:
    *   **Script Worker**: Gemini 2.5 Flash.
    *   **Voice Worker**: Google Cloud TTS (Neural2/Journey).
    *   **Image Worker**: Gemini 2.5 Flash Image.
    *   **Render Worker**: MoviePy + FFmpeg (Horizontal -> Vertical Sync).

### 4. Publishing & Auth
*   **OAuth**: Multi-channel YouTube API integration.
*   **Secrets**: Token rotation and storage via GCP Secret Manager.

## Data Flow
1.  **Scheduler** checks brand quotas and triggers **Editorial Agent**.
2.  **Agent** decides topic and generates **Editorial Package**.
3.  **Verification Layer** scores the package for quality and uniqueness.
4.  **Pipeline Job** is triggered; downloads assets, renders MP4, and uploads to GCS.
5.  **Publishing Logic** retrieves MP4 and metadata, then pushes to YouTube.
6.  **Memory Update** stores the topic and performance metrics back in Firestore.
