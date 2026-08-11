"""
content_strategy.py

Content Portfolio Strategy Manager for ATLAS.
Dynamically manages content portfolio allocations based on evidence.
"""

from typing import Dict, Any
from src.atlas.models import PortfolioCategory, EvidenceLevel


class ContentStrategyEngine:
    """
    Maintains and balances content portfolio allocations per channel.
    Categories: CORE, GROWTH, AUTHORITY, EXPERIMENTAL, SEASONAL, TREND_RESPONSIVE, EVERGREEN.
    """

    # Baseline recommended portfolio distributions
    DEFAULT_PORTFOLIO = {
        PortfolioCategory.CORE.value: 0.40,
        PortfolioCategory.GROWTH.value: 0.20,
        PortfolioCategory.AUTHORITY.value: 0.15,
        PortfolioCategory.EVERGREEN.value: 0.15,
        PortfolioCategory.EXPERIMENTAL.value: 0.10,
    }

    @classmethod
    def select_portfolio_category(cls, brand_id: str, historical_performance: dict) -> Dict[str, Any]:
        """
        Determines the optimal portfolio category for the next content item based on performance evidence.
        """
        recent_winners = historical_performance.get("recent_winners", [])
        recent_failures = historical_performance.get("recent_failures", [])
        
        # If experimental content is winning, boost EXPERIMENTAL / GROWTH allocation
        if len(recent_failures) > len(recent_winners) and len(recent_failures) > 3:
            return {
                "category": PortfolioCategory.CORE,
                "reasoning": "High recent failure rate detected. Re-anchoring to battle-tested CORE portfolio pillar.",
                "evidence_level": EvidenceLevel.OBSERVED.value,
            }
        elif len(recent_winners) > 2:
            return {
                "category": PortfolioCategory.GROWTH,
                "reasoning": "Strong recent performance. Allocating slot to GROWTH initiative for audience expansion.",
                "evidence_level": EvidenceLevel.OBSERVED.value,
            }
        else:
            return {
                "category": PortfolioCategory.CORE,
                "reasoning": "Standard balanced portfolio allocation.",
                "evidence_level": EvidenceLevel.INFERRED.value,
            }
