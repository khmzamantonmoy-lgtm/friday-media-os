"""
theme.py

SaaS Design System for FRIDAY Media OS.
Provides dark-first styling, enterprise color tokens, card layouts,
status badges, KPI metric cards, and responsive components.
"""

import streamlit as st


def apply_saas_theme():
    """Injects custom CSS to transform Streamlit into a SaaS application (Linear/Vercel style)."""
    st.markdown(
        """
        <style>
        /* Modern Dark SaaS Theme Tokens */
        :root {
            --bg-primary: #0F172A;
            --bg-card: #1E293B;
            --bg-card-hover: #334155;
            --border-color: #334155;
            --text-primary: #F8FAFC;
            --text-secondary: #94A3B8;
            --accent-blue: #2563EB;
            --accent-blue-hover: #1D4ED8;
            --status-success: #22C55E;
            --status-warning: #F59E0B;
            --status-danger: #EF4444;
        }

        /* App Background */
        .stApp {
            background-color: var(--bg-primary);
            color: var(--text-primary);
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
        }

        /* Sidebar Styling */
        [data-testid="stSidebar"] {
            background-color: #090D16 !important;
            border-right: 1px solid var(--border-color);
        }

        /* Card Container */
        .saas-card {
            background-color: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 20px;
            margin-bottom: 20px;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
            transition: border-color 0.2s ease;
        }
        .saas-card:hover {
            border-color: #475569;
        }

        /* Agent Card Header */
        .agent-card-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 14px;
        }
        .agent-title {
            font-size: 1.15rem;
            font-weight: 700;
            color: #F8FAFC;
            display: flex;
            align-items: center;
            gap: 10px;
        }

        /* Status Badges */
        .badge {
            display: inline-block;
            padding: 4px 10px;
            border-radius: 9999px;
            font-size: 0.75rem;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }
        .badge-success {
            background-color: rgba(34, 197, 94, 0.15);
            color: #4ADE80;
            border: 1px solid rgba(34, 197, 94, 0.3);
        }
        .badge-warning {
            background-color: rgba(245, 158, 11, 0.15);
            color: #FBBF24;
            border: 1px solid rgba(245, 158, 11, 0.3);
        }
        .badge-danger {
            background-color: rgba(239, 68, 68, 0.15);
            color: #FCA5A5;
            border: 1px solid rgba(239, 68, 68, 0.3);
        }
        .badge-blue {
            background-color: rgba(37, 99, 235, 0.15);
            color: #60A5FA;
            border: 1px solid rgba(37, 99, 235, 0.3);
        }

        /* KPI Metric Container */
        .kpi-container {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
            gap: 12px;
            margin-top: 12px;
        }
        .kpi-box {
            background-color: #0F172A;
            border: 1px solid var(--border-color);
            border-radius: 8px;
            padding: 12px;
            text-align: center;
        }
        .kpi-label {
            font-size: 0.75rem;
            color: var(--text-secondary);
            text-transform: uppercase;
            margin-bottom: 4px;
        }
        .kpi-value {
            font-size: 1.25rem;
            font-weight: 700;
            color: #F8FAFC;
        }

        /* Buttons */
        .stButton>button {
            border-radius: 8px !important;
            font-weight: 600 !important;
            border: 1px solid var(--border-color) !important;
            background-color: #1E293B !important;
            color: #F8FAFC !important;
            transition: all 0.15s ease !important;
        }
        .stButton>button:hover {
            background-color: var(--accent-blue) !important;
            border-color: var(--accent-blue) !important;
            color: #FFFFFF !important;
        }

        /* Input Fields */
        .stTextInput>div>div>input, .stSelectbox>div>div>div, .stTextArea>div>div>textarea {
            background-color: #0F172A !important;
            color: #F8FAFC !important;
            border-color: var(--border-color) !important;
            border-radius: 8px !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_header(title: str, subtitle: str, badge: str = "PROD"):
    """Renders a SaaS header bar with subtitle and operational status badge."""
    apply_saas_theme()
    st.markdown(
        f"""
        <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 24px; border-bottom: 1px solid #334155; padding-bottom: 16px;">
            <div>
                <h1 style="margin:0; font-size: 1.85rem; font-weight: 800; color: #F8FAFC;">{title}</h1>
                <p style="margin:4px 0 0 0; color: #94A3B8; font-size: 0.95rem;">{subtitle}</p>
            </div>
            <div>
                <span class="badge badge-blue">⚡ SYSTEM {badge}</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
