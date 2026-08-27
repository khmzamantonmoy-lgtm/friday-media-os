"""
dashboard/pages/3_Posted_Content.py

Posted Content Media Management Interface for FRIDAY Media OS.
Displays published videos across channels with status, YouTube links, quality metrics,
and GCS video asset links.
"""

import sys
import os
import streamlit as st
from google.cloud import firestore

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from dashboard.theme import apply_saas_theme, render_header
from src.config.firestore_schema import BRAND_PROFILES

st.set_page_config(page_title="Posted Content - FRIDAY Media OS", layout="wide")

apply_saas_theme()
render_header("Posted Content", "Media Management & Verified Distribution Archive Catalog", badge="ARCHIVE")

db = firestore.Client(project=os.environ.get("GCP_PROJECT_ID", "friday-media-prod"))

# Query posted/scheduled content
try:
    posted_docs = list(
        db.collection("scheduled_posts")
        .where("status", "==", "posted")
        .order_by("posted_at", direction=firestore.Query.DESCENDING)
        .stream()
    )
except Exception:
    posted_docs = []

st.markdown('<div class="saas-card">', unsafe_allow_html=True)
st.markdown("### 📽 Published Video Archive")
st.caption("Historical log of successfully verified distributions across YouTube channels.")

if not posted_docs:
    st.info("No published videos found yet.")
else:
    for doc in posted_docs:
        sp = doc.to_dict()
        b_id = sp.get("brand_id", "—")
        b_name = BRAND_PROFILES.get(b_id, {}).get("display_name", b_id)
        yt_url = sp.get("youtube_url", "")
        posted_at = sp.get("posted_at", "—")

        c1, c2, c3, c4 = st.columns([3, 2, 1, 1])
        with c1:
            st.markdown(f"**{sp.get('chosen_title') or sp.get('topic')}**")
            st.caption(f"Brand: `{b_name}` · Platform: `{sp.get('platform', 'YouTube')}` · ID: `{sp.get('content_id')}`")
        with c2:
            st.write(f"📅 Published: {posted_at}")
        with c3:
            st.markdown('<span class="badge badge-success">DELIVERED</span>', unsafe_allow_html=True)
        with c4:
            if yt_url:
                st.link_button("▶ View on YouTube", yt_url)
            else:
                st.caption("No URL")

st.markdown('</div>', unsafe_allow_html=True)
