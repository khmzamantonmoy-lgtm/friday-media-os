"""
theme.py

SaaS Design System for FRIDAY Media OS.
Provides light-first professional styling, enterprise color tokens, card layouts,
status badges, KPI metric cards, and responsive components.
"""

import streamlit as st


def apply_saas_theme():
    """Injects custom CSS to transform Streamlit into a light SaaS application (Vercel/Linear style)."""
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=Montserrat:wght@400;500;600;700&display=swap');

        /* Modern Light SaaS Theme Tokens */
        :root {
            --bg-primary: #F8FAFC;
            --bg-card: #FFFFFF;
            --bg-card-hover: #F1F5F9;
            --border-color: #E2E8F0;
            --border-strong: #CBD5E1;
            --text-primary: #0F172A;
            --text-secondary: #475569;
            --text-muted: #64748B;
            --accent-blue: #2563EB;
            --accent-blue-hover: #1D4ED8;
            --status-success: #059669;
            --status-warning: #D97706;
            --status-danger: #DC2626;
            
            /* Sidebar Contrast (Dark Sidebar) */
            --bg-sidebar: #0F172A;
            --text-sidebar: #F8FAFC;
            --text-sidebar-muted: #94A3B8;
        }

        /* App Background */
        .stApp {
            background-color: var(--bg-primary);
            color: var(--text-primary);
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
        }

        /* Sidebar Styling (High contrast, dark sidebar) */
        [data-testid="stSidebar"] {
            background-color: var(--bg-sidebar) !important;
            border-right: 1px solid var(--border-color);
        }
        
        [data-testid="stSidebar"] * {
            color: var(--text-sidebar) !important;
        }
        
        [data-testid="stSidebar"] a:hover {
            background-color: rgba(255, 255, 255, 0.05) !important;
        }

        /* Card Container */
        .saas-card {
            background-color: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 24px;
            margin-bottom: 24px;
            box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.05), 0 1px 2px 0 rgba(0, 0, 0, 0.03);
            transition: all 0.2s ease;
        }
        .saas-card:hover {
            border-color: var(--border-strong);
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05), 0 2px 4px -1px rgba(0, 0, 0, 0.03);
        }

        /* Agent Card Header */
        .agent-card-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 16px;
        }
        
        .agent-title {
            font-family: 'Montserrat', sans-serif;
            font-size: 1.15rem;
            font-weight: 700;
            color: var(--text-primary);
            display: flex;
            align-items: center;
            gap: 8px;
        }
        
        .agent-status-tag {
            font-size: 0.75rem;
            padding: 2px 8px;
            border-radius: 4px;
            font-weight: 600;
            background: var(--surface-blue);
            color: var(--accent-blue);
        }

        /* Status Badges */
        .badge {
            display: inline-flex;
            align-items: center;
            padding: 3px 10px;
            border-radius: 9999px;
            font-size: 0.75rem;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.025em;
        }
        .badge-success { background: rgba(5, 150, 105, 0.1); color: var(--status-success); border: 1px solid rgba(5, 150, 105, 0.2); }
        .badge-warning { background: rgba(217, 119, 6, 0.1); color: var(--status-warning); border: 1px solid rgba(217, 119, 6, 0.2); }
        .badge-danger { background: rgba(220, 38, 38, 0.1); color: var(--status-danger); border: 1px solid rgba(220, 38, 38, 0.2); }
        .badge-blue { background: rgba(37, 99, 235, 0.1); color: var(--accent-blue); border: 1px solid rgba(37, 99, 235, 0.2); }

        /* KPI Grid */
        .kpi-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
            gap: 16px;
            margin-top: 16px;
        }
        .kpi-item {
            display: flex;
            flex-direction: column;
            padding: 12px;
            background-color: var(--bg-primary);
            border: 1px solid var(--border-color);
            border-radius: 8px;
        }
        .kpi-label {
            font-size: 0.75rem;
            color: var(--text-secondary);
            text-transform: uppercase;
            margin-bottom: 4px;
            font-weight: 600;
            letter-spacing: 0.025em;
        }
        .kpi-value {
            font-size: 1.35rem;
            font-weight: 700;
            color: var(--text-primary);
        }

        /* Operations Log Feed */
        .log-feed {
            max-height: 400px;
            overflow-y: auto;
            padding-right: 8px;
        }
        .log-entry {
            display: flex;
            gap: 12px;
            padding: 12px 0;
            border-bottom: 1px solid var(--border-color);
        }
        .log-entry:last-child { border-bottom: none; }
        .log-time {
            font-size: 0.75rem;
            color: var(--text-muted);
            min-width: 70px;
            font-family: monospace;
        }
        .log-content {
            font-size: 0.85rem;
            color: var(--text-primary);
        }
        .log-icon {
            font-size: 0.85rem;
            display: flex;
            align-items: center;
        }

        /* Pipeline Stepper */
        .pipeline-track {
            display: flex;
            justify-content: space-between;
            margin-top: 24px;
            position: relative;
            padding: 0 10px;
        }
        .pipeline-track::before {
            content: '';
            position: absolute;
            top: 14px;
            left: 0;
            right: 0;
            height: 2px;
            background: var(--border-color);
            z-index: 1;
        }
        .step-node {
            display: flex;
            flex-direction: column;
            align-items: center;
            z-index: 2;
            width: 80px;
        }
        .node-circle {
            width: 30px;
            height: 30px;
            border-radius: 50%;
            background: var(--bg-card);
            border: 2px solid var(--border-color);
            display: flex;
            align-items: center;
            justify-content: center;
            margin-bottom: 8px;
            font-size: 0.75rem;
            transition: all 0.3s ease;
            color: var(--text-secondary);
        }
        .node-label {
            font-size: 0.65rem;
            color: var(--text-muted);
            text-transform: uppercase;
            font-weight: 600;
            text-align: center;
        }
        .node-active .node-circle { border-color: var(--accent-blue); color: var(--accent-blue); box-shadow: 0 0 12px rgba(37, 99, 235, 0.2); }
        .node-complete .node-circle { background: var(--status-success); border-color: var(--status-success); color: white; }
        .node-waiting .node-circle { background: var(--bg-primary); border-color: var(--border-color); color: var(--text-muted); }
        .node-failed .node-circle { background: var(--status-danger); border-color: var(--status-danger); color: white; }

        /* Hide Streamlit Header/Footer */
        #MainMenu {visibility: hidden;}
        footer {visibility: hidden;}
        header {visibility: hidden;}
        
        /* Premium button styles */
        .stButton>button {
            border-radius: 8px !important;
            font-weight: 600 !important;
            border: 1px solid var(--border-color) !important;
            background-color: var(--bg-card) !important;
            color: var(--text-primary) !important;
            transition: all 0.15s ease !important;
        }
        .stButton>button:hover {
            background-color: var(--bg-card-hover) !important;
            border-color: var(--border-strong) !important;
            color: var(--accent-blue) !important;
        }
        
        /* Accent elements */
        .accent-text {
            color: var(--accent-blue);
            font-weight: 600;
        }
        
        /* Metric Styling Overwrite */
        [data-testid="stMetricValue"] {
            font-size: 1.85rem !important;
            font-weight: 800 !important;
            color: var(--text-primary) !important;
        }
        [data-testid="stMetricLabel"] {
            font-size: 0.75rem !important;
            font-weight: 600 !important;
            text-transform: uppercase !important;
            color: var(--text-secondary) !important;
            letter-spacing: 0.05em !important;
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
        <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 32px; padding-bottom: 16px; border-bottom: 1px solid var(--border-color);">
            <div>
                <h1 style="margin:0; font-family: 'Montserrat', sans-serif; font-size: 1.85rem; font-weight: 800; letter-spacing: -0.025em; color: var(--text-primary);">{title}</h1>
                <p style="margin:4px 0 0 0; color: var(--text-secondary); font-size: 0.95rem; font-weight: 400;">{subtitle}</p>
            </div>
            <div style="display: flex; gap: 16px; align-items: center;">
                <div style="text-align: right; margin-right: 8px;">
                    <div style="font-size: 0.75rem; color: var(--text-muted); text-transform: uppercase; font-weight: 600; letter-spacing: 0.05em;">AI ENGINE Status</div>
                    <div style="font-size: 0.85rem; color: var(--status-success); font-weight: 700;">● AUTONOMOUS NOMINAL</div>
                </div>
                <span class="badge badge-blue">{badge}</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
