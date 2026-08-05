"""
dashboard/pages/1_Editorial_Calendar.py

Editorial Calendar Management Interface for FRIDAY Media OS.
Allows optional manual topic scheduling and displays agent-assigned topics,
priority levels, source attribution, quality scores, and scheduling state.
"""

import sys
import os
import datetime
import streamlit as st
from google.cloud import firestore

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from dashboard.theme import apply_saas_theme, render_header
from src.config.firestore_schema import BRAND_PROFILES

st.set_page_config(page_title="Editorial Calendar - FRIDAY Media OS", layout="wide")

apply_saas_theme()
render_header("Editorial Calendar", "Brand Content Planning & Google Agent Assignment Matrix", badge="PLANNER")

db = firestore.Client(project=os.environ.get("GCP_PROJECT_ID", "friday-media-prod"))

# --- Add Calendar Assignment Form ---
with st.expander("➕ Add Optional Manual Topic Assignment"):
    with st.form("add_calendar_item"):
        col1, col2, col3 = st.columns([2, 1, 1])
        with col1:
            cal_topic = st.text_input("Editorial Topic", placeholder="e.g. 'Stoic Lessons on Crisis Leadership'")
        with col2:
            cal_brand = st.selectbox("Target Brand", options=list(BRAND_PROFILES.keys()), format_func=lambda b: BRAND_PROFILES[b]["display_name"])
        with col3:
            cal_priority = st.selectbox("Priority", ["high", "medium", "low"])

        col_date, col_notes = st.columns([1, 2])
        with col_date:
            cal_date = st.date_input("Scheduled Date", value=datetime.date.today())
        with col_notes:
            cal_notes = st.text_input("Editorial Notes / Guidelines", placeholder="Focus on executive risk")

        submitted = st.form_submit_button("Add Assignment")
        if submitted:
            if not cal_topic.strip():
                st.error("Topic is required.")
            else:
                db.collection("editorial_calendar").add({
                    "brand": cal_brand,
                    "topic": cal_topic,
                    "priority": cal_priority,
                    "date": datetime.datetime.combine(cal_date, datetime.time(12, 0)),
                    "notes": cal_notes,
                    "status": "pending",
                    "processed": False,
                    "source": "manual",
                    "created_at": firestore.SERVER_TIMESTAMP,
                })
                st.success(f"Added topic '{cal_topic}' for {BRAND_PROFILES[cal_brand]['display_name']}.")
                st.rerun()

st.write("")

# --- Filter Bar ---
col_f1, col_f2 = st.columns([1, 1])
with col_f1:
    filter_brand = st.selectbox("Filter by Brand", ["All Brands"] + list(BRAND_PROFILES.keys()))
with col_f2:
    filter_status = st.selectbox("Filter by Status", ["All Statuses", "pending", "processed"])

# Query Calendar Items
query = db.collection("editorial_calendar").order_by("date", direction=firestore.Query.ASCENDING)
if filter_brand != "All Brands":
    query = query.where("brand", "==", filter_brand)
if filter_status != "All Statuses":
    query = query.where("status", "==", filter_status)

items = list(query.limit(50).stream())

st.markdown('<div class="saas-card">', unsafe_allow_html=True)
st.markdown("### 📅 Editorial Assignment Queue")
st.caption("If the queue is empty, Google Agents automatically determine and generate topics.")

if not items:
    st.info("No topic assignments found matching the filter. Agents are operating in Autonomous Mode.")
else:
    table_data = []
    for doc in items:
        d = doc.to_dict()
        brand_name = BRAND_PROFILES.get(d.get("brand"), {}).get("display_name", d.get("brand"))
        dt = d.get("date")
        dt_str = dt.strftime("%Y-%m-%d") if isinstance(dt, datetime.datetime) else str(dt)

        table_data.append({
            "Brand": brand_name,
            "Topic": d.get("topic", "—"),
            "Priority": d.get("priority", "medium").upper(),
            "Source": d.get("source", "agent").upper(),
            "Scheduled Date": dt_str,
            "Status": d.get("status", "pending").upper(),
            "Notes": d.get("notes", "—"),
        })

    st.dataframe(table_data, use_container_width=True, hide_index=True)

st.markdown('</div>', unsafe_allow_html=True)
