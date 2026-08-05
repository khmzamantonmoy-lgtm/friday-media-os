"""
job_trigger.py

Replaces any direct import/call of pipeline_coordinator from the Streamlit app.
The UI process must never run the pipeline in-process — that's what turned a
web request into a long-lived FFmpeg render inside Cloud Shell. Instead, the
UI fires a Cloud Run Job execution and returns immediately; progress is read
back from Firestore, which pipeline_coordinator.py already writes to.

Usage in dashboard/app.py:

    from src.job_trigger import trigger_pipeline_job

    if st.button("Generate Content"):
        execution_name = trigger_pipeline_job(
            brand_id=selected_brand,
            topic=topic_input,
            content_id=new_content_id,
        )
        st.session_state["last_execution"] = execution_name
"""

import os
from google.cloud import run_v2

PROJECT_ID = os.environ.get("GCP_PROJECT_ID", "friday-media-prod")
REGION = os.environ.get("GCP_REGION", "us-central1")
JOB_NAME = os.environ.get("PIPELINE_JOB_NAME", "media-pipeline")


def trigger_pipeline_job(brand_id: str, topic: str, content_id: str) -> str:
    """
    Starts one execution of the friday-media-pipeline Cloud Run Job with
    per-run overrides. Returns the execution resource name so the UI can
    reference it, though status is tracked via Firestore content_items,
    not by polling the Job execution itself.
    """
    client = run_v2.JobsClient()
    job_path = client.job_path(PROJECT_ID, REGION, JOB_NAME)

    request = run_v2.RunJobRequest(
        name=job_path,
        overrides=run_v2.RunJobRequest.Overrides(
            container_overrides=[
                run_v2.RunJobRequest.Overrides.ContainerOverride(
                    env=[
                        run_v2.EnvVar(name="BRAND_ID", value=brand_id),
                        run_v2.EnvVar(name="TOPIC", value=topic),
                        run_v2.EnvVar(name="CONTENT_ID", value=content_id),
                    ]
                )
            ]
        ),
    )

    operation = client.run_job(request=request)
    execution = operation.metadata  # Execution is available via the LRO metadata
    return execution.name if execution else "submitted"
