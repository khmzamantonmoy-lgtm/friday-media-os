"""
dashboard/Home.py

Streamlit UI for FRIDAY Media OS - Operations Center & Manual Studio.
Executive-grade SaaS dashboard with light professional theme, KPIs,
live brand monitoring, and manual generation control.
"""

import sys
import os
import uuid
import random
import streamlit as st
from google.cloud import firestore

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.job_trigger import trigger_pipeline_job
from src.config.firestore_schema import BRAND_PROFILES
from dashboard.theme import apply_saas_theme, render_header

st.set_page_config(page_title="Operations Center - FRIDAY Media OS", layout="wide")

apply_saas_theme()
render_header("Operations Center", "Enterprise AI Media Operations & Manual Studio Command", badge="LIVE")

db = firestore.Client(project=os.environ.get("GCP_PROJECT_ID", "friday-media-prod"))

# Pre-fetch stats for Executive KPIs
try:
    total_videos = len(list(db.collection("content_items").stream()))
except Exception:
    total_videos = 0

try:
    active_agents = len(BRAND_PROFILES)
except Exception:
    active_agents = 4

try:
    pending_uploads = len(list(db.collection("scheduled_posts").where("status", "==", "pending").stream()))
except Exception:
    pending_uploads = 0

# --- Executive Metric Cards ---
st.markdown("### 📊 Platform Executive Summary")
col_m1, col_m2, col_m3, col_m4 = st.columns(4)
with col_m1:
    st.metric(label="Active AI Channels", value=str(active_agents), delta="100% Online")
with col_m2:
    st.metric(label="Total Generated Videos", value=str(total_videos), delta="All Brands")
with col_m3:
    st.metric(label="Pending Scheduled Uploads", value=str(pending_uploads), delta="Auto Queue")
with col_m4:
    st.metric(label="System Operations", value="NOMINAL", delta="Pipeline Live")

st.write("")

# --- Brand Fleet Monitoring ---
st.markdown("### 🧠 Brand Fleet Operations")
brand_cols = st.columns(4)
for idx, (b_id, profile) in enumerate(BRAND_PROFILES.items()):
    with brand_cols[idx]:
        st.markdown(f'<div class="saas-card">', unsafe_allow_html=True)
        st.markdown(f'<div class="agent-title">📌 {profile["display_name"]}</div>', unsafe_allow_html=True)
        st.caption(f"Brand ID: `{b_id}`")
        
        # Pull stats from Firestore for this brand if available
        try:
            brand_vids = len(list(db.collection("content_items").where("brand_id", "==", b_id).stream()))
        except Exception:
            brand_vids = 0
            
        st.markdown(
            f"""
            <div style="margin: 12px 0;">
                <div style="font-size: 0.75rem; color: var(--text-secondary); text-transform: uppercase;">Topic Strategy</div>
                <div style="font-size: 0.95rem; font-weight: 700; color: var(--text-primary);">{profile.get("topic_strategy", "AI-driven").upper()}</div>
            </div>
            <div style="margin: 12px 0;">
                <div style="font-size: 0.75rem; color: var(--text-secondary); text-transform: uppercase;">Voice Profile</div>
                <div style="font-size: 0.85rem; font-family: monospace; color: var(--text-primary);">{profile.get("voice_id", "Default")}</div>
            </div>
            <div style="margin: 12px 0;">
                <div style="font-size: 0.75rem; color: var(--text-secondary); text-transform: uppercase;">Generated Clips</div>
                <div style="font-size: 1.1rem; font-weight: 700; color: var(--accent-blue);">{brand_vids}</div>
            </div>
            """, 
            unsafe_allow_html=True
        )
        st.markdown('</div>', unsafe_allow_html=True)

st.write("")

# Sample prompt ideas generator
TOPIC_IDEAS = {
    "bd_threatpulse": [
        "Why Zero Trust Architecture Matters for Boardroom Risk Compliance",
        "Executive Ransomware Incident Response: 5 Critical C-Suite Decisions",
        "AI Supply Chain Threats & Enterprise Vulnerability Mitigation 2026",
    ],
    "wealthwise": [
        "Index Funds vs Real Estate: Where to Allocate $10,000 Today",
        "High-Yield Savings & Federal Reserve Rate Decision Impact",
        "How Compound Interest Creates Generational Wealth in 20 Years",
    ],
    "kids_universe": [
        "Why is the Sky Blue? Magical Atmospheric Science for Kids",
        "How Do Whales Communicate Across the Ocean?",
        "Space Exploration: What is Inside Jupiter's Great Red Spot?",
    ],
    "philosophy": [
        "Marcus Aurelius on Controlling Your Mind in Chaotic Times",
        "The Stoic Dichotomy of Control: Focus on What You Can Master",
        "Seneca on the Shortness of Life & Meaningful Time Management",
    ],
}

# --- Creator Studio Panel ---
col_form, col_preset = st.columns([2, 1])

with col_form:
    st.markdown('<div class="saas-card">', unsafe_allow_html=True)
    st.markdown('<div class="agent-title">🎬 Manual Studio Generator</div>', unsafe_allow_html=True)
    st.caption("Craft custom prompts or generate one-off videos for any brand profile.")

    with st.form("create_content_form"):
        selected_brand = st.selectbox(
            "Target Brand Profile",
            options=list(BRAND_PROFILES.keys()),
            format_func=lambda b: f"{BRAND_PROFILES[b]['display_name']} ({b})",
        )

        preset_topic = st.session_state.get("prompt_idea", "")
        topic_input = st.text_area(
            "Topic & Custom Prompt Angle",
            value=preset_topic,
            placeholder="e.g. 'Why Zero Trust architecture matters for the board'",
            height=100,
        )

        col_b1, col_b2 = st.columns([1, 1])
        with col_b1:
            submitted = st.form_submit_button("🚀 Generate Video")

        if submitted:
            if not topic_input.strip():
                st.error("Please provide a topic or prompt angle.")
            else:
                content_id = f"manual_{selected_brand}_{str(uuid.uuid4())[:8]}"
                
                # Create initial draft doc in Firestore
                db.collection("content_items").document(content_id).set({
                    "brand_id": selected_brand,
                    "topic": topic_input,
                    "status": "draft",
                    "source": "manual",
                    "created_at": firestore.SERVER_TIMESTAMP,
                    "updated_at": firestore.SERVER_TIMESTAMP,
                })
                db.collection("content_queue").document(content_id).set({
                    "brand_id": selected_brand,
                    "topic": topic_input,
                    "status": "QUEUED",
                    "source": "manual",
                    "created_at": firestore.SERVER_TIMESTAMP,
                    "updated_at": firestore.SERVER_TIMESTAMP,
                })
                
                execution = trigger_pipeline_job(selected_brand, topic_input, content_id)
                st.session_state["last_content_id"] = content_id
                st.success(f"Pipeline triggered! Tracking ID: `{content_id}`")

    st.markdown('</div>', unsafe_allow_html=True)

with col_preset:
    st.markdown('<div class="saas-card">', unsafe_allow_html=True)
    st.markdown('<div class="agent-title">💡 Prompt Inspiration</div>', unsafe_allow_html=True)
    st.caption("Quickly test new ideas using pre-configured brand concepts.")

    for b_id, b_profile in BRAND_PROFILES.items():
        with st.expander(f"📌 {b_profile['display_name']}"):
            for idea in TOPIC_IDEAS.get(b_id, []):
                if st.button(f"Use: {idea[:40]}...", key=f"idea_{b_id}_{hash(idea)}"):
                    st.session_state["prompt_idea"] = idea
                    st.rerun()

    if st.button("🎲 Random Surprise Idea"):
        all_ideas = [i for ideas in TOPIC_IDEAS.values() for i in ideas]
        st.session_state["prompt_idea"] = random.choice(all_ideas)
        st.rerun()

    st.markdown('</div>', unsafe_allow_html=True)

# --- Recent Studio Items Tracker ---
st.markdown('<div class="saas-card">', unsafe_allow_html=True)
st.markdown('<div class="agent-title">📊 Recent Manual Studio Pipeline Runs</div>', unsafe_allow_html=True)

STATUS_BADGES = {
    "draft": ("badge-blue", "DRAFT"),
    "generating_script": ("badge-warning", "SCRIPTING"),
    "generating_audio": ("badge-warning", "VOICE AI"),
    "generating_images": ("badge-warning", "IMAGEN 3"),
    "rendering": ("badge-warning", "RENDERING"),
    "published": ("badge-success", "READY"),
    "ready": ("badge-success", "READY"),
    "posted": ("badge-success", "PUBLISHED"),
    "delivered": ("badge-success", "DELIVERED"),
    "failed": ("badge-danger", "FAILED"),
}

try:
    items = (
        db.collection("content_items")
        .order_by("created_at", direction=firestore.Query.DESCENDING)
        .limit(10)
        .stream()
    )
    items_list = list(items)
except Exception:
    items_list = []

if not items_list:
    st.info("No recent pipeline runs found.")
else:
    for doc in items_list:
        data = doc.to_dict()
        raw_status = data.get("status", "draft")
        badge_class, status_text = STATUS_BADGES.get(raw_status, ("badge-blue", raw_status.upper()))

        c1, c2, c3, c4 = st.columns([3, 1, 1, 1])
        with c1:
            st.markdown(f"**{data.get('topic', '—')}**")
            st.caption(f"Brand: `{data.get('brand_id', '—')}` · Source: `{data.get('source', 'manual')}` · ID: `{doc.id}`")
        with c2:
            st.markdown(f'<span class="badge {badge_class}">{status_text}</span>', unsafe_allow_html=True)
        with c3:
            if data.get("final_video_uri"):
                st.caption("📹 Video Rendered")
            else:
                st.caption("⏳ In Progress")
        with c4:
            if data.get("final_video_uri"):
                st.link_button("View Assets", "Upload_Schedule")

st.markdown('</div>', unsafe_allow_html=True)
