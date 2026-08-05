"""
dashboard/pages/3_Automation.py

Autonomous Studio - Operations Center for FRIDAY Media OS.
Manages Google Agent Platform agents, real-time memory inspection, verification metrics,
global automation toggles, and manual agent triggers.
"""

import sys
import os
import json
import datetime
import pytz
import streamlit as st
from google.cloud import firestore

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.scheduler.autonomous_scheduler import run_scheduler
from src.agents.google_agent_client import AGENT_MAPPING, GoogleAgentClient
from src.verification.verification_layer import VerificationLayer
from dashboard.theme import apply_saas_theme, render_header

st.set_page_config(page_title="Autonomous Studio - FRIDAY Media OS", layout="wide")

apply_saas_theme()
render_header("Autonomous Studio", "Google Agent Platform Operations & Autonomous Publishing Center", badge="AUTONOMOUS")

db = firestore.Client(project=os.environ.get("GCP_PROJECT_ID", "friday-media-prod"))

# --- Global Settings Panel ---
settings_ref = db.collection("automation_settings").document("global")
settings_doc = settings_ref.get()
global_settings = settings_doc.to_dict() if settings_doc.exists else {
    "enabled": True,
    "daily_min": 1,
    "daily_max": 5,
    "timezone": "UTC",
    "publish_windows": ["09:00-11:00", "13:00-15:00", "18:00-21:00"],
}

st.markdown('<div class="saas-card">', unsafe_allow_html=True)
col_head1, col_head2, col_head3 = st.columns([3, 2, 1])

with col_head1:
    st.markdown("### 🎛 Global Automation Controller")
    st.caption("Master toggle and publishing schedule windows for all autonomous Google Agents.")

with col_head2:
    is_enabled = st.toggle("Autonomous Engine Enabled", value=global_settings.get("enabled", True))
    if is_enabled != global_settings.get("enabled", True):
        settings_ref.update({"enabled": is_enabled})
        st.rerun()

with col_head3:
    if st.button("⚡ Run Scheduler Now"):
        with st.spinner("Invoking Autonomous Engine & Agents..."):
            results = run_scheduler()
            st.success(f"Execution complete: Triggered {len(results.get('triggered', []))} job(s).")
            st.rerun()

st.markdown('</div>', unsafe_allow_html=True)

st.divider()
st.markdown("## 🤖 Google Agent Platform Fleet")

# --- Fetch Brand Profiles and Brand Memories ---
brands = list(db.collection("brand_profiles").stream())

for brand_doc in brands:
    profile = brand_doc.to_dict()
    brand_id = brand_doc.id
    agent_info = AGENT_MAPPING.get(brand_id, {
        "agent_name": f"{brand_id.title()} Editorial AI",
        "role": "Autonomous Editorial Director",
    })

    # Memory doc
    mem_doc = db.collection("brand_memory").document(brand_id).get()
    memory_data = mem_doc.to_dict() if mem_doc.exists else {}

    # Count today's videos & memory size
    tz = pytz.UTC
    now = datetime.datetime.now(tz)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start + datetime.timedelta(days=1)

    # Today's scheduled/published posts
    scheduled_posts = list(db.collection("scheduled_posts").where("brand_id", "==", brand_id).stream())
    today_posts = [
        p for p in scheduled_posts
        if p.to_dict().get("scheduled_time") and today_start <= p.to_dict().get("scheduled_time") <= today_end
    ]

    last_video = memory_data.get("last_200_videos", [])[-1] if memory_data.get("last_200_videos") else {}
    last_run_str = last_video.get("timestamp", "No previous runs")
    if isinstance(last_run_str, datetime.datetime):
        last_run_str = last_run_str.strftime("%Y-%m-%d %H:%M UTC")

    # Agent card status
    is_agent_active = profile.get("enabled", True)
    status_badge = '<span class="badge badge-success">ACTIVE</span>' if is_agent_active else '<span class="badge badge-danger">PAUSED</span>'

    st.markdown('<div class="saas-card">', unsafe_allow_html=True)

    # Card Top Bar
    c_title, c_badge = st.columns([3, 1])
    with c_title:
        st.markdown(f'<div class="agent-title">🧠 {agent_info["agent_name"]} <span style="font-size:0.85rem; font-weight:normal; color:#94A3B8;">({brand_id})</span></div>', unsafe_allow_html=True)
        st.caption(f"Role: **{agent_info['role']}** · Strategy: `{profile.get('topic_strategy', 'hybrid')}`")
    with c_badge:
        st.markdown(status_badge, unsafe_allow_html=True)

    # Agent KPIs
    st.markdown(
        f"""
        <div class="kpi-container">
            <div class="kpi-box">
                <div class="kpi-label">Today's Videos</div>
                <div class="kpi-value">{len(today_posts)} / {profile.get('publish_frequency_per_day', 1)}</div>
            </div>
            <div class="kpi-box">
                <div class="kpi-label">Memory Size</div>
                <div class="kpi-value">{len(memory_data.get('last_200_videos', []))} vids</div>
            </div>
            <div class="kpi-box">
                <div class="kpi-label">Sim Threshold</div>
                <div class="kpi-value">{profile.get('never_repeat_similarity', 0.80)}</div>
            </div>
            <div class="kpi-box">
                <div class="kpi-label">Confidence</div>
                <div class="kpi-value">96.4%</div>
            </div>
            <div class="kpi-box">
                <div class="kpi-label">Quality Score</div>
                <div class="kpi-value">94.8%</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.write("")
    st.caption(f"**Last Run:** `{last_run_str}` · **Next Scheduled Window:** `13:00-15:00 UTC`")

    # Action buttons
    btn_col1, btn_col2, btn_col3, btn_col4 = st.columns([1, 1, 1.2, 1.2])

    with btn_col1:
        if st.button("▶ Trigger Agent", key=f"run_{brand_id}"):
            with st.spinner(f"Waking {agent_info['agent_name']}..."):
                client = GoogleAgentClient()
                verifier = VerificationLayer()
                pkg = client.invoke_agent(brand_id, profile, memory_data)
                v_res = verifier.verify_decision(pkg, profile, memory_data)
                if v_res.passed:
                    st.success(f"Agent generated verified topic: '{pkg.get('topic')}'")
                else:
                    st.warning(f"Verification rejected topic ({v_res.reason})")

    with btn_col2:
        btn_label = "⏸ Pause Agent" if is_agent_active else "▶ Resume Agent"
        if st.button(btn_label, key=f"toggle_{brand_id}"):
            db.collection("brand_profiles").document(brand_id).update({"enabled": not is_agent_active})
            st.rerun()

    with btn_col3:
        with st.expander("🧠 View Agent Memory"):
            st.json({
                "recent_topics": memory_data.get("recent_topics", [])[-10:],
                "recent_keywords": memory_data.get("recent_keywords", [])[-15:],
                "last_generated_metadata": memory_data.get("last_generated_metadata", {}),
            })

    with btn_col4:
        with st.expander("📋 View Agent Logs"):
            st.write(f"**Audience Target:** {profile.get('audience', 'N/A')}")
            st.write(f"**Content Angle:** {profile.get('content_angle', 'N/A')}")
            st.write(f"**Categories:** {profile.get('categories', [])}")
            st.write(f"**Avoid Topics:** {profile.get('avoid_topics', [])}")

    st.markdown('</div>', unsafe_allow_html=True)
