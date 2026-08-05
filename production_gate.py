"""
production_gate.py

Executes exactly ONE production run for each of the four Editorial AI brains.
Used as a Production Validation Gate.
"""

import os
os.environ["GOOGLE_CLOUD_PROJECT"] = "friday-media-prod"
os.environ["GCP_PROJECT_ID"] = "friday-media-prod"

import datetime
import logging
import json
import time
from google.cloud import firestore
from src.job_trigger import trigger_pipeline_job
from src.agents.google_agent_client import GoogleAgentClient
from src.verification.verification_layer import VerificationLayer
from src.config.brand_registry import BRAND_REGISTRY

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("production_gate")

def run_gate():
    db = firestore.Client(project="friday-media-prod")
    agent_client = GoogleAgentClient(project_id="friday-media-prod")
    verifier = VerificationLayer()
    
    results = []

    for brand_id, profile in BRAND_REGISTRY.items():
        logger.info(f"--- VALIDATION RUN: {brand_id} ---")
        
        # 1. Fetch Memory
        mem_doc = db.collection("brand_memory").document(brand_id).get()
        memory_data = mem_doc.to_dict() if mem_doc.exists else {}
        
        # 2. Invoke Agent (Research & Decision)
        logger.info(f"[{brand_id}] Invoking Editorial Agent...")
        agent_package = agent_client.invoke_agent(
            brand_id=brand_id,
            brand_profile=profile,
            brand_memory=memory_data
        )
        
        # 3. Verification Layer
        logger.info(f"[{brand_id}] Running Verification Layer...")
        v_res = verifier.verify_decision(agent_package, profile, memory_data)
        
        if not v_res.passed:
            logger.error(f"[{brand_id}] Verification FAILED: {v_res.reason}")
            results.append({
                "brand": brand_id,
                "status": "FAILED_VERIFICATION",
                "reason": v_res.reason
            })
            continue
            
        # 4. Create Records
        content_id = f"gate_{brand_id}_{datetime.datetime.now().strftime('%m%d_%H%M')}"
        topic = agent_package.get("topic")
        
        logger.info(f"[{brand_id}] Storing records for {content_id}...")
        
        db.collection("content_items").document(content_id).set({
            "brand_id": brand_id,
            "topic": topic,
            "status": "draft",
            "source": "gate",
            "agent_name": agent_package.get("agent_name"),
            "category": agent_package.get("category"),
            "editorial_reasoning": agent_package.get("editorial_reasoning"),
            "confidence": agent_package.get("confidence"),
            "quality_score": agent_package.get("quality_score"),
            "verification_status": v_res.status,
            "similarity_score": v_res.metrics.get("effective_similarity"),
            "seo_title": agent_package.get("seo_title"),
            "caption": agent_package.get("description"),
            "hashtags": agent_package.get("hashtags", []),
            "script": agent_package.get("script_narration"),
            "scene_plan": agent_package.get("scene_plan", []),
            "created_at": firestore.SERVER_TIMESTAMP,
            "updated_at": firestore.SERVER_TIMESTAMP,
        })

        db.collection("content_queue").document(content_id).set({
            "brand_id": brand_id,
            "topic": topic,
            "status": "QUEUED",
            "source": "gate",
            "created_at": firestore.SERVER_TIMESTAMP,
            "updated_at": firestore.SERVER_TIMESTAMP,
        }, merge=True)
        
        # 5. Trigger Pipeline
        logger.info(f"[{brand_id}] Triggering Cloud Run Job...")
        try:
            exec_name = trigger_pipeline_job(brand_id, topic, content_id)
            logger.info(f"[{brand_id}] Job triggered: {exec_name}")
            results.append({
                "brand": brand_id,
                "status": "TRIGGERED",
                "content_id": content_id,
                "execution": exec_name,
                "topic": topic,
                "reason": agent_package.get("editorial_reasoning"),
                "verification_score": v_res.status,
                "confidence": agent_package.get("confidence"),
                "script": agent_package.get("script_narration")[:100] + "..."
            })
        except Exception as e:
            logger.exception(f"[{brand_id}] Trigger failed")
            results.append({
                "brand": brand_id,
                "status": "TRIGGER_FAILED",
                "error": str(e)
            })
        
        logger.info("Staggering triggers (120s delay)...")
        time.sleep(120)

    print("\n--- GATE TRIGGER SUMMARY ---")
    print(json.dumps(results, indent=2))
    print("\nNext: Wait for Rendering to complete, then run publishing.")

if __name__ == "__main__":
    run_gate()
