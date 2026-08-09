"""
dashboard/pages/0_Production_Control.py

Production Control Panel — FRIDAY Media OS.
Per-brand verified-public tracking with full pipeline state visibility.
Only counts a video as verified-public when PublicationVerifier confirms:
  uploadStatus=processed AND privacyStatus=public AND captions AND metadata AND thumbnail.

Status semantics:
  GREEN  = verified-public, all acceptance conditions satisfied
  YELLOW = processing/pending
  RED    = failed/blocking
  GREY   = no cycle currently running
"""

import sys
import os
import datetime
import pytz
import streamlit as st
from google.cloud import firestore

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.config.brand_registry import BRAND_REGISTRY
from dashboard.theme import apply_saas_theme, render_header

st.set_page_config(
    page_title="Production Control — FRIDAY Media OS",
    layout="wide",
    page_icon="🎬",
)

apply_saas_theme()
render_header(
    "Production Control Panel",
    "Per-Brand Verified-Public Pipeline — Live Status",
    badge="LIVE",
)

db = firestore.Client(project=os.environ.get("GCP_PROJECT_ID", "friday-media-prod"))

BRAND_DISPLAY = {
    "bd_threatpulse":  "🔵 BD ThreatPulse",
    "wealthwise":      "🟢 WealthWise Daily",
    "kids_universe":   "🟠 Tiny Sparks",
    "philosophy":      "🟣 The Thinking Room",
}

ACTIVE_STATUSES = {
    "NEW", "TOPIC_SELECTED", "SCRIPT_READY", "ASSETS_READY",
    "RENDERING", "RENDERED", "UPLOADING", "PUBLIC",
    "CAPTIONS_VERIFIED", "MEMORY_UPDATED", "RETRY",
}

PIPELINE_EMOJI = {
    "NEW":              "🆕",
    "TOPIC_SELECTED":   "💡",
    "SCRIPT_READY":     "📝",
    "ASSETS_READY":     "🖼",
    "RENDERING":        "🎬",
    "RENDERED":         "✅",
    "UPLOADING":        "⬆️",
    "PUBLIC":           "⏳",
    "CAPTIONS_VERIFIED":"📋",
    "MEMORY_UPDATED":   "🧠",
    "COMPLETE":         "🏁",
    "FAILED":           "❌",
    "RETRY":            "🔄",
}


def status_badge(label, color):
    colors = {
        "green":  ("#16a34a", "#dcfce7"),
        "yellow": ("#b45309", "#fef3c7"),
        "red":    ("#dc2626", "#fee2e2"),
        "grey":   ("#6b7280", "#f3f4f6"),
        "blue":   ("#2563eb", "#dbeafe"),
    }
    fg, bg = colors.get(color, colors["grey"])
    return (
        f'<span style="background:{bg};color:{fg};padding:2px 10px;'
        f'border-radius:12px;font-size:0.78rem;font-weight:700;'
        f'letter-spacing:0.05em;">{label}</span>'
    )


def get_brand_data(brand_id):
    today = datetime.datetime.now(pytz.UTC).replace(
        hour=0, minute=0, second=0, microsecond=0
    ).replace(tzinfo=None)
    daily_target = BRAND_REGISTRY.get(brand_id, {}).get("daily_target", 4)

    all_items = list(
        db.collection("content_items").where("brand_id", "==", brand_id).stream()
    )

    verified_public = [
        d for d in all_items
        if d.to_dict().get("status") == "COMPLETE"
        and d.to_dict().get("youtube_verified") is True
    ]
    active_items = [
        d for d in all_items
        if d.to_dict().get("status") in ACTIVE_STATUSES
    ]
    failed_items = [
        d for d in all_items
        if d.to_dict().get("status") == "FAILED"
    ]
    public_pending = [
        d for d in all_items
        if d.to_dict().get("status") == "PUBLIC"
        and not d.to_dict().get("youtube_verified")
    ]

    def _ca(d):
        ca = d.to_dict().get("created_at")
        if isinstance(ca, str):
            try:
                return datetime.datetime.fromisoformat(ca.replace("Z", "+00:00")).replace(tzinfo=None)
            except Exception:
                return datetime.datetime.min
        return ca if ca else datetime.datetime.min

    latest_active = None
    latest_active_status = None
    if active_items:
        s = sorted(active_items, key=_ca, reverse=True)[0]
        latest_active = s.to_dict()
        latest_active_status = latest_active.get("status")

    latest_complete = None
    complete_items = [d for d in all_items if d.to_dict().get("status") == "COMPLETE"]
    if complete_items:
        latest_complete = sorted(complete_items, key=_ca, reverse=True)[0].to_dict()

    dlq_count = len(list(
        db.collection("dead_letter_queue").where("brand_id", "==", brand_id).stream()
    ))

    mem_doc = db.collection("brand_memory").document(brand_id).get()
    mem_data = mem_doc.to_dict() if mem_doc.exists else {}
    mem_count = len(mem_data.get("memories", []))
    mem_updated = str(mem_data.get("last_updated", "Never"))[:19]

    queue_docs = list(
        db.collection("content_queue")
        .where("brand_id", "==", brand_id)
        .where("created_at", ">=", today)
        .stream()
    )
    cycles_requested = len(queue_docs)
    cycles_running = sum(1 for d in queue_docs if d.to_dict().get("status") in ACTIVE_STATUSES)
    cycles_completed = sum(1 for d in queue_docs if d.to_dict().get("status") == "COMPLETE")

    missing = max(0, daily_target - len(verified_public) - len(active_items))

    return {
        "daily_target": daily_target,
        "verified_public_count": len(verified_public),
        "active_count": len(active_items),
        "failed_count": len(failed_items),
        "public_pending_count": len(public_pending),
        "missing": missing,
        "latest_active_status": latest_active_status,
        "latest_active": latest_active,
        "latest_complete": latest_complete,
        "dlq_count": dlq_count,
        "mem_count": mem_count,
        "mem_updated": mem_updated,
        "cycles_requested": cycles_requested,
        "cycles_running": cycles_running,
        "cycles_completed": cycles_completed,
    }


# Scoreboard
st.markdown("## 📊 Daily Production Contract")
st.caption(
    "A video is only counted Verified-Public when: "
    "`uploadStatus=processed` AND `privacyStatus=public` AND captions AND metadata AND thumbnail."
)

total_verified = 0
contract_pass = True
scoreboard_cols = st.columns(4)
brand_data_cache = {}

for idx, brand_id in enumerate(BRAND_REGISTRY.keys()):
    data = get_brand_data(brand_id)
    brand_data_cache[brand_id] = data
    v = data["verified_public_count"]
    t = data["daily_target"]
    total_verified += v
    if v < t:
        contract_pass = False
    with scoreboard_cols[idx]:
        if v >= t:
            bg, fg, icon = "#dcfce7", "#16a34a", "✅"
        elif v > 0:
            bg, fg, icon = "#fef3c7", "#b45309", "⏳"
        else:
            bg, fg, icon = "#fee2e2", "#dc2626", "🔴"
        st.markdown(
            f'<div style="background:{bg};border-radius:12px;padding:16px;text-align:center;border:1px solid #e2e8f0;">'
            f'<div style="font-size:1.8rem;font-weight:900;color:{fg}">{icon} {v}/{t}</div>'
            f'<div style="font-size:0.85rem;font-weight:600;color:#374151;margin-top:4px;">{BRAND_DISPLAY.get(brand_id, brand_id)}</div>'
            f'<div style="font-size:0.75rem;color:#6b7280;">Verified Public Today</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

st.markdown("---")
contract_label = f"✅ PASS — {total_verified}/16" if contract_pass else f"❌ FAIL — {total_verified}/16"
c_bg = "#dcfce7" if contract_pass else "#fee2e2"
c_fg = "#16a34a" if contract_pass else "#dc2626"
st.markdown(
    f'<div style="text-align:center;padding:12px;background:{c_bg};border-radius:8px;'
    f'font-size:1.1rem;font-weight:700;color:{c_fg};">Production Contract: {contract_label} Verified Public</div>',
    unsafe_allow_html=True,
)
st.write("")

# Per-brand detail
st.markdown("## 🏭 Per-Brand Pipeline Detail")

for brand_id in BRAND_REGISTRY.keys():
    data = brand_data_cache[brand_id]
    v = data["verified_public_count"]
    t = data["daily_target"]

    if v >= t:
        status_color, status_label = "green", "TARGET MET"
    elif data["active_count"] > 0:
        status_color, status_label = "yellow", "PRODUCING"
    elif data["failed_count"] > 0 and data["active_count"] == 0:
        status_color, status_label = "red", "BLOCKED"
    else:
        status_color, status_label = "grey", "IDLE"

    with st.expander(
        f"{BRAND_DISPLAY.get(brand_id, brand_id)}  —  {v}/{t} Verified Public  [{status_label}]",
        expanded=True,
    ):
        cols = st.columns([2, 2, 2, 2, 2])

        with cols[0]:
            st.markdown("**Target / Verified**")
            st.markdown(status_badge(f"{v}/{t} Verified Public", status_color), unsafe_allow_html=True)
            st.write("")
            st.metric("Missing Slots", data["missing"])
            st.metric("Pending Verification", data["public_pending_count"])

        with cols[1]:
            st.markdown("**Cycle Counts**")
            st.metric("Cycles Requested", data["cycles_requested"])
            st.metric("Cycles Running", data["cycles_running"])
            st.metric("Cycles Completed", data["cycles_completed"])
            st.metric("Active in Pipeline", data["active_count"])
            st.metric("Failed Items (total)", data["failed_count"])

        with cols[2]:
            st.markdown("**Current Pipeline State**")
            active_s = data["latest_active_status"]
            if active_s:
                emoji = PIPELINE_EMOJI.get(active_s, "❓")
                clr = "red" if active_s == "FAILED" else "yellow" if active_s in ("RETRY", "PUBLIC") else "blue"
                st.markdown(status_badge(f"{emoji} {active_s}", clr), unsafe_allow_html=True)
                la = data["latest_active"] or {}
                st.caption(f"Topic: {str(la.get('topic', ''))[:50]}")
                st.caption(f"YT ID: {la.get('youtube_video_id', '—')}")
            else:
                st.markdown(status_badge("⬜ NO ACTIVE CYCLE", "grey"), unsafe_allow_html=True)

        with cols[3]:
            st.markdown("**Latest Publication**")
            lc = data.get("latest_complete") or {}
            yt_id = lc.get("youtube_video_id", "—")
            yt_v = lc.get("youtube_verified")
            st.write(f"📹 YT ID: `{yt_id}`")
            st.markdown(
                status_badge("✅ VERIFIED", "green") if yt_v else status_badge("⏳ PENDING", "yellow"),
                unsafe_allow_html=True,
            )
            st.write("")
            meta = lc.get("metadata", {})
            has_title = bool(meta.get("title_suggestions") or lc.get("title"))
            st.write(f"📋 Captions: {'✅' if lc.get('srt_uri') or yt_v else '❓'}")
            st.write(f"🏷 Metadata: {'✅' if has_title else '❓'}")
            st.write(f"🖼 Thumbnail: {'✅' if yt_v else '❓'}")

        with cols[4]:
            st.markdown("**Memory & DLQ**")
            st.metric("brand_memory entries", data["mem_count"])
            st.write(f"Updated: `{data['mem_updated']}`")
            if data["dlq_count"] > 0:
                st.markdown(status_badge(f"⚠️ DLQ: {data['dlq_count']}", "red"), unsafe_allow_html=True)
            else:
                st.markdown(status_badge("DLQ: 0 ✅", "green"), unsafe_allow_html=True)

            st.write("")
            st.markdown("**Blocker**")
            if v >= t:
                st.markdown(status_badge("None — Target Met ✅", "green"), unsafe_allow_html=True)
            elif data["public_pending_count"] > 0 and data["active_count"] == 0:
                st.markdown(
                    status_badge(f"⏳ {data['public_pending_count']} awaiting YouTube", "yellow"),
                    unsafe_allow_html=True,
                )
            elif data["failed_count"] > 0 and data["active_count"] == 0:
                st.markdown(status_badge("❌ All cycles FAILED", "red"), unsafe_allow_html=True)
            elif data["missing"] > 0 and data["active_count"] == 0:
                st.markdown(
                    status_badge(f"🕐 {data['missing']} slots waiting for scheduler", "grey"),
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(status_badge("Pipeline executing…", "yellow"), unsafe_allow_html=True)

st.markdown("---")
now_utc = datetime.datetime.now(pytz.UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
st.caption(
    f"Last refreshed: `{now_utc}` — "
    "Uploaded ≠ Published. Pipeline-complete ≠ Verified. "
    "Only `youtube_verified=True` AND `status=COMPLETE` counts toward the daily target."
)
if st.button("🔄 Refresh"):
    st.rerun()
