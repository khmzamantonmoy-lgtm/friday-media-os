"""
dashboard/pages/2_Upload_Schedule.py

Streamlit page for Upload & Scheduling.
Allows users to review AI metadata, edit titles/captions/hashtags, restore AI suggestions,
regenerate metadata, schedule published content to YouTube, or publish immediately.
Stores records in Firestore collection: scheduled_posts
"""

import datetime
import streamlit as st
from google.cloud import firestore
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from dashboard.theme import apply_saas_theme, render_header

st.set_page_config(page_title="Upload & Schedule — FRIDAY Media OS", layout="wide")

apply_saas_theme()
render_header("Upload & Schedule", "Social Platform Distribution & AI Metadata Refinement Panel", badge="PUBLISHER")

db = firestore.Client(project=os.environ.get("GCP_PROJECT_ID", "friday-media-prod"))

# Query published content items
try:
    published_docs = list(db.collection("content_items").where("status", "==", "published").stream())
except Exception:
    published_docs = []

if not published_docs:
    st.info("No published content available for scheduling yet. Generate content on the Home page first.")
else:
    options_map = {}
    for doc in published_docs:
        data = doc.to_dict()
        label = f"[{data.get('brand_id')}] {data.get('topic')} ({doc.id})"
        options_map[label] = (doc.id, data)

    st.markdown('<div class="saas-card">', unsafe_allow_html=True)
    st.markdown("### 📽 Select Asset to Schedule or Publish")
    selected_label = st.selectbox("Select Published Content", options=list(options_map.keys()))
    content_id, content_data = options_map[selected_label]
    st.markdown('</div>', unsafe_allow_html=True)

    # Initialize or update session state for selection
    if "selected_content_id" not in st.session_state or st.session_state.selected_content_id != content_id:
        st.session_state.selected_content_id = content_id
        st.session_state.original_titles = content_data.get("title_suggestions", [])
        st.session_state.original_caption = content_data.get("caption", "")
        st.session_state.original_hashtags = content_data.get("hashtags", [])
        
        st.session_state.chosen_title = st.session_state.original_titles[0] if st.session_state.original_titles else content_data.get("seo_title", content_data.get("topic", ""))
        st.session_state.chosen_caption = st.session_state.original_caption
        st.session_state.chosen_hashtags = ", ".join(st.session_state.original_hashtags)

    # 1. AI Metadata Editor Section
    st.markdown('<div class="saas-card">', unsafe_allow_html=True)
    st.markdown("### 📝 AI Metadata Refinement")

    # Title Editor
    titles = st.session_state.original_titles
    default_title = titles[0] if titles else ""
    title_label = "Final Video Title"
    if st.session_state.chosen_title != default_title:
        title_label += " ✏️ (Edited)"
    
    st.session_state.chosen_title = st.text_input(title_label, value=st.session_state.chosen_title)

    if titles:
        st.markdown("**AI Suggested Titles (click to apply):**")
        t_cols = st.columns(len(titles))
        for idx, t in enumerate(titles):
            with t_cols[idx]:
                if st.button(f"Option {idx+1}: {t[:30]}...", key=f"use_t_{idx}"):
                    st.session_state.chosen_title = t
                    st.rerun()
            
    if st.button("Restore Original Title", key="restore_title"):
        st.session_state.chosen_title = default_title
        st.rerun()

    st.divider()

    # Caption Editor
    caption_label = "Description / Caption"
    if st.session_state.chosen_caption != st.session_state.original_caption:
        caption_label += " ✏️ (Edited)"
    
    st.session_state.chosen_caption = st.text_area(caption_label, value=st.session_state.chosen_caption, height=140)
    
    if st.button("Restore Original Caption", key="restore_caption"):
        st.session_state.chosen_caption = st.session_state.original_caption
        st.rerun()

    st.divider()

    # Hashtags Editor
    hashtags_label = "Hashtags (comma-separated)"
    original_tags_str = ", ".join(st.session_state.original_hashtags)
    if st.session_state.chosen_hashtags != original_tags_str:
        hashtags_label += " ✏️ (Edited)"
        
    st.session_state.chosen_hashtags = st.text_input(hashtags_label, value=st.session_state.chosen_hashtags)
    
    if st.button("Restore Original Hashtags", key="restore_hashtags"):
        st.session_state.chosen_hashtags = original_tags_str
        st.rerun()

    st.divider()

    # Closed Captions (CC) Status
    srt_uri = content_data.get("srt_uri")
    if srt_uri:
        st.markdown('<span class="badge badge-success">✅ Closed Captions (SRT) Ready</span>', unsafe_allow_html=True)
    else:
        st.markdown('<span class="badge badge-warning">⚠️ No Captions File</span>', unsafe_allow_html=True)

    st.write("")

    # Regenerate Metadata Button
    if st.button("🔄 Regenerate Metadata with Gemini", key="regenerate_meta"):
        with st.spinner("Regenerating metadata with Gemini..."):
            try:
                from src.config.firestore_schema import get_brand
                from src.workers.metadata_worker import generate_metadata
                
                brand_id = content_data.get("brand_id")
                brand = get_brand(db, brand_id)
                script = content_data.get("script")
                
                if not script:
                    raise ValueError("No script found on content item to regenerate metadata.")
                    
                new_metadata = generate_metadata(script, brand)
                
                db.collection("content_items").document(content_id).update({
                    "title_suggestions": new_metadata.get("title_suggestions", []),
                    "caption": new_metadata.get("caption", ""),
                    "hashtags": new_metadata.get("hashtags", []),
                    "updated_at": firestore.SERVER_TIMESTAMP
                })
                
                st.session_state.original_titles = new_metadata.get("title_suggestions", []),
                st.session_state.original_caption = new_metadata.get("caption", "")
                st.session_state.original_hashtags = new_metadata.get("hashtags", [])
                
                st.session_state.chosen_title = st.session_state.original_titles[0] if st.session_state.original_titles else ""
                st.session_state.chosen_caption = st.session_state.original_caption
                st.session_state.chosen_hashtags = ", ".join(st.session_state.original_hashtags)
                
                st.success("Metadata regenerated successfully!")
                st.rerun()
            except Exception as e:
                st.error(f"Failed to regenerate metadata: {e}")

    st.markdown('</div>', unsafe_allow_html=True)

    # 2. Scheduling Form
    st.markdown('<div class="saas-card">', unsafe_allow_html=True)
    st.markdown("### 📅 Distribution Schedule Config")

    with st.form("schedule_post_form"):
        col1, col2 = st.columns(2)
        with col1:
            platform = st.selectbox("Platform Target", options=["YouTube", "TikTok", "Instagram"])
            date = st.date_input("Scheduled Date", value=datetime.date.today())
        with col2:
            time = st.time_input("Scheduled Time", value=datetime.datetime.now().time())

        submit = st.form_submit_button("🗓 Confirm & Schedule Post")

        if submit:
            scheduled_time = datetime.datetime.combine(date, time)
            tags_list = [t.strip() for t in st.session_state.chosen_hashtags.split(",") if t.strip()]

            post_doc = {
                "content_id": content_id,
                "brand_id": content_data.get("brand_id"),
                "topic": content_data.get("topic"),
                "platform": platform,
                "scheduled_time": scheduled_time,
                "status": "pending",
                "created_at": datetime.datetime.now(datetime.UTC),
                "ai_title": default_title,
                "ai_caption": st.session_state.original_caption,
                "ai_hashtags": st.session_state.original_hashtags,
                "chosen_title": st.session_state.chosen_title,
                "chosen_caption": st.session_state.chosen_caption,
                "chosen_hashtags": tags_list
            }

            db.collection("scheduled_posts").add(post_doc)
            db.collection("content_queue").document(content_id).update({
                "status": "SCHEDULED",
                "updated_at": firestore.SERVER_TIMESTAMP
            })
            st.success(f"Post scheduled for {platform} on {scheduled_time.strftime('%Y-%m-%d %H:%M:%S')}!")
            st.rerun()

    st.markdown('</div>', unsafe_allow_html=True)

# 3. Scheduled Posts Queue Display
st.markdown('<div class="saas-card">', unsafe_allow_html=True)
st.markdown("### 📋 Scheduled Posts Queue")

try:
    scheduled_docs = list(db.collection("scheduled_posts").order_by("scheduled_time", direction=firestore.Query.ASCENDING).stream())
except Exception:
    scheduled_docs = []

if not scheduled_docs:
    st.info("No posts scheduled yet.")
else:
    for doc in scheduled_docs:
        sp = doc.to_dict()
        doc_id = doc.id
        status = sp.get("status", "pending")
        
        badge_class = "badge-warning" if status == "pending" else "badge-success"

        c1, c2, c3, c4 = st.columns([3, 2, 1, 1])
        with c1:
            st.markdown(f"**{sp.get('chosen_title') or sp.get('topic')}**")
            st.caption(f"Brand: `{sp.get('brand_id')}` · Platform: `{sp.get('platform')}` · ID: `{sp.get('content_id')}`")
        with c2:
            st.write(f"⏰ {sp.get('scheduled_time')}")
        with c3:
            st.markdown(f'<span class="badge {badge_class}">{status.upper()}</span>', unsafe_allow_html=True)
        with c4:
            if status == "pending":
                if st.button("🚀 Publish Now", key=f"pub_{doc_id}"):
                    with st.spinner("Publishing directly to YouTube..."):
                        try:
                            from src.workers.youtube_worker import upload_video
                            
                            c_id = sp.get("content_id")
                            b_id = sp.get("brand_id")
                            
                            c_doc = db.collection("content_items").document(c_id).get()
                            if not c_doc.exists:
                                st.error("Content item not found.")
                            else:
                                c_info = c_doc.to_dict()
                                v_uri = c_info.get("final_video_uri")
                                s_uri = c_info.get("srt_uri")
                                
                                title_to_use = sp.get("chosen_title") or sp.get("ai_title")
                                desc_to_use = sp.get("chosen_caption") or sp.get("ai_caption")
                                tags_to_use = sp.get("chosen_hashtags") or sp.get("ai_hashtags", [])
                                
                                youtube_url = upload_video(
                                    channel=b_id,
                                    content_id=c_id,
                                    video_gs_uri=v_uri,
                                    title=title_to_use,
                                    description=desc_to_use,
                                    hashtags=tags_to_use,
                                    srt_gs_uri=s_uri
                                )
                                
                                db.collection("scheduled_posts").document(doc_id).update({
                                    "status": "posted",
                                    "youtube_url": youtube_url,
                                    "posted_at": datetime.datetime.now(datetime.UTC)
                                })
                                db.collection("content_queue").document(c_id).update({
                                    "status": "PUBLISHED",
                                    "updated_at": firestore.SERVER_TIMESTAMP
                                })
                                st.success(f"Published to YouTube! URL: {youtube_url}")
                                st.rerun()
                        except Exception as e:
                            st.error(f"Publish failed: {e}")

st.markdown('</div>', unsafe_allow_html=True)
