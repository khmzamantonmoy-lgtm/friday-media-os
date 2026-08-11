"""
audience_intel.py

Audience Intelligence & Geographic Targeting for ATLAS.
Default Target Geography: United States.
"""

from typing import Dict, Any, List
from src.atlas.models import EvidenceLevel


class AudienceIntelligence:
    """
    Provides geographic and audience segment intelligence.
    Ensures content is tailored for US audience interests, cultural context,
    and search behavior without faking relevance.
    """

    US_CULTURAL_CONTEXT = {
        "bd_threatpulse": {
            "terminology": ["CISO", "SEC compliance", "zero-trust", "Ransomware protection", "DOJ cybersecurity guidelines"],
            "target_segments": ["US C-suite Executives", "Enterprise Security Directors", "Tech Risk Officers"],
            "key_interests": ["US regulatory compliance", "supply chain risk", "cloud security architecture"],
        },
        "wealthwise": {
            "terminology": ["S&P 500", "401(k)", "Roth IRA", "Fed rate decision", "treasury yields", "index funds"],
            "target_segments": ["US Retail Investors", "Individual Wealth Builders", "401k Optimizers"],
            "key_interests": ["passive index investing", "inflation hedging", "US market volatility"],
        },
        "kids_universe": {
            "terminology": ["STEM education", "Curious mind", "Fun science", "Nature facts", "Outer space"],
            "target_segments": ["US Elementary Students", "Parents", "Homeschooling Families"],
            "key_interests": ["Visual science experiments", "Nature exploration", "Space discoveries"],
        },
        "philosophy": {
            "terminology": ["Stoicism", "Marcus Aurelius", "Seneca", "Self-Mastery", "Amor Fati", "Memento Mori"],
            "target_segments": ["US Professionals", "Self-Improvement Enthusiasts", "Daily Stoic Practitioners"],
            "key_interests": ["Practical daily resilience", "Stress reduction", "Mental clarity in fast-paced tech/finance"],
        },
    }

    @classmethod
    def get_geographic_briefing(cls, brand_id: str, target_geo: str = "US") -> Dict[str, Any]:
        brand_context = cls.US_CULTURAL_CONTEXT.get(brand_id, {
            "terminology": ["Industry standard"],
            "target_segments": [f"{target_geo} Viewers"],
            "key_interests": ["Core topics"],
        })
        
        return {
            "target_geography": target_geo,
            "evidence_level": EvidenceLevel.INFERRED.value,
            "terminology": brand_context["terminology"],
            "target_segments": brand_context["target_segments"],
            "key_interests": brand_context["key_interests"],
        }

    @classmethod
    def evaluate_geographic_response(cls, performance_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyzes performance metrics to detect if an alternative geography is outperforming.
        Distinguishes OBSERVED, INFERRED, and HYPOTHESIS data.
        """
        geo_views = performance_data.get("geographic_distribution", {})
        if not geo_views:
            return {
                "top_geography": "US",
                "evidence_level": EvidenceLevel.HYPOTHESIS.value,
                "note": "Insufficient geographic analytics data. Defaulting to US strategy.",
            }
        
        sorted_geos = sorted(geo_views.items(), key=lambda x: x[1], reverse=True)
        top_geo = sorted_geos[0][0] if sorted_geos else "US"
        
        return {
            "top_geography": top_geo,
            "geographic_distribution": geo_views,
            "evidence_level": EvidenceLevel.OBSERVED.value if len(geo_views) > 10 else EvidenceLevel.INFERRED.value,
            "action": f"Optimize strategy for {top_geo} audience demand." if top_geo != "US" else "Maintain US market focus.",
        }
