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
            --bg-primary: #090E1A;
            --bg-card: #111827;
            --bg-card-hover: #1F2937;
            --border-color: #1F2937;
            --text-primary: #F9FAFB;
            --text-secondary: #9CA3AF;
            --accent-blue: #3B82F6;
            --accent-blue-hover: #2563EB;
            --status-success: #10B981;
            --status-warning: #F59E0B;
            --status-danger: #EF4444;
            --bg-sidebar: #05070A;
        }

        /* App Background */
        .stApp {
            background-color: var(--bg-primary);
            color: var(--text-primary);
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
        }

        /* Sidebar Styling */
        [data-testid="stSidebar"] {
            background-color: var(--bg-sidebar) !important;
            border-right: 1px solid var(--border-color);
        }

        /* Card Container */
        .saas-card {
            background-color: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 24px;
            margin-bottom: 20px;
            box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.1), 0 1px 2px 0 rgba(0, 0, 0, 0.06);
            transition: all 0.2s ease;
        }
        .saas-card:hover {
            border-color: #374151;
        }

        /* Agent Card Styles */
        .agent-card-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 16px;
        }
        .agent-title {
            font-size: 1.1rem;
            font-weight: 700;
            color: var(--text-primary);
            display: flex;
            align-items: center;
            gap: 8px;
        }
        .agent-status-tag {
            font-size: 0.7rem;
            padding: 2px 8px;
            border-radius: 4px;
            font-weight: 600;
            background: rgba(59, 130, 246, 0.1);
            color: var(--accent-blue);
        }

        /* Status Badges */
        .badge {
            display: inline-flex;
            align-items: center;
            padding: 2px 10px;
            border-radius: 9999px;
            font-size: 0.7rem;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.025em;
        }
        .badge-success { background: rgba(16, 185, 129, 0.1); color: #34D399; border: 1px solid rgba(16, 185, 129, 0.2); }
        .badge-warning { background: rgba(245, 158, 11, 0.1); color: #FBBF24; border: 1px solid rgba(245, 158, 11, 0.2); }
        .badge-danger { background: rgba(239, 68, 68, 0.1); color: #F87171; border: 1px solid rgba(239, 68, 68, 0.2); }
        .badge-blue { background: rgba(59, 130, 246, 0.1); color: #60A5FA; border: 1px solid rgba(59, 130, 246, 0.2); }

        /* KPI Grid */
        .kpi-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
            gap: 16px;
            margin-top: 16px;
        }
        .kpi-item {
            display: flex;
            flex-direction: column;
        }
        .kpi-label {
            font-size: 0.7rem;
            color: var(--text-secondary);
            text-transform: uppercase;
            margin-bottom: 4px;
            font-weight: 500;
        }
        .kpi-value {
            font-size: 1.25rem;
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
            border-bottom: 1px solid #1F2937;
        }
        .log-entry:last-child { border-bottom: none; }
        .log-time {
            font-size: 0.75rem;
            color: var(--text-secondary);
            min-width: 60px;
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
            background: #1F2937;
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
            background: #111827;
            border: 2px solid #1F2937;
            display: flex;
            align-items: center;
            justify-content: center;
            margin-bottom: 8px;
            font-size: 0.7rem;
            transition: all 0.3s ease;
        }
        .node-label {
            font-size: 0.65rem;
            color: var(--text-secondary);
            text-transform: uppercase;
            font-weight: 600;
            text-align: center;
        }
        .node-active .node-circle { border-color: var(--accent-blue); color: var(--accent-blue); box-shadow: 0 0 12px rgba(59, 130, 246, 0.4); }
        .node-complete .node-circle { background: var(--status-success); border-color: var(--status-success); color: white; }
        .node-waiting .node-circle { background: #111827; border-color: #1F2937; color: #4B5563; }
        .node-failed .node-circle { background: var(--status-danger); border-color: var(--status-danger); color: white; }

        /* Hide Streamlit Header/Footer */
        #MainMenu {visibility: hidden;}
        footer {visibility: hidden;}
        header {visibility: hidden;}
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_header(title: str, subtitle: str, badge: str = "PROD"):
    """Renders a SaaS header bar with subtitle and operational status badge."""
    apply_saas_theme()
    st.markdown(
        f"""
        <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 32px; padding-bottom: 16px;">
            <div>
                <h1 style="margin:0; font-size: 1.75rem; font-weight: 800; letter-spacing: -0.025em; color: #F9FAFB;">{title}</h1>
                <p style="margin:4px 0 0 0; color: #9CA3AF; font-size: 0.9rem; font-weight: 400;">{subtitle}</p>
            </div>
            <div style="display: flex; gap: 12px; align-items: center;">
                <div style="text-align: right; margin-right: 12px;">
                    <div style="font-size: 0.65rem; color: #9CA3AF; text-transform: uppercase; font-weight: 600;">System Health</div>
                    <div style="font-size: 0.85rem; color: #10B981; font-weight: 700;">● NOMINAL</div>
                </div>
                <span class="badge badge-blue">{badge}</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
