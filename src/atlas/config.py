"""
config.py

Configuration and Model Routing for ATLAS.
"""

import os

# ATLAS Deployment Mode
# True = ATLAS operates in Shadow Mode (logs decisions and QA without blocking production)
# False = Active Governance Mode (enforces ATLAS briefs and QA gating)
ATLAS_SHADOW_MODE = os.environ.get("ATLAS_SHADOW_MODE", "true").lower() in ("true", "1", "t")

# Target Geography Configuration
DEFAULT_TARGET_GEOGRAPHY = "US"

# Configurable Model Routing based on task complexity
# Using available Gemini models
MODEL_ROUTING = {
    "FAST_LOW_COST": "gemini-2.5-flash",    # Filtering, classification, metadata
    "STRONG_GENERAL": "gemini-2.5-flash",   # Strategic reasoning, briefs, performance analysis
    "HIGH_REASONING": "gemini-2.5-flash",   # Portfolio decisions, deep learning mechanism derivation
}
