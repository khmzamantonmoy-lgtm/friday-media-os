"""
dashboard/Home.py

Streamlit UI for FRIDAY Media OS - Manual Studio.
Creator-focused studio for manual content creation, custom prompt editing,
one-off generation, and pipeline triggering.
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

st.set_page_config(page_title="Manual Studio - FRIDAY Media OS", layout="wide")

apply_saas_theme()
render_header("Manual Studio", "Creator Operations & One-Off AI Video Generation", badge="STUDIO")

db = firestore.Client()

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

items = (
    db.collection("content_items")
    .order_by("created_at", direction=firestore.Query.DESCENDING)
    .limit(10)
    .stream()
)

for doc in items:
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
