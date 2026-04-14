"""Framework 1: Market Breakdown System (Tier 1 — weekly).

TAM/SAM/SOM, demand trends, underserved opportunities, capital flows.
"""

from __future__ import annotations

import re
from typing import Any

from sovereign_swarm.strategic_intel.models import (
    ExternalSignal,
    FrameworkTier,
    MarketBreakdownOutput,
)


class MarketBreakdownFramework:
    name = "market_breakdown"
    tier = FrameworkTier.AUTOMATED
    description = "TAM/SAM/SOM, demand trends, underserved opportunities, capital flows"

    @staticmethod
    def get_search_queries(tenant: str, brand: Any) -> list[str]:
        industry = MarketBreakdownFramework._extract_industry(brand)
        return [
            f"{industry} market size TAM 2025 2026",
            f"{brand.target_audience} market demand trends",
            f"{industry} competitors market share analysis",
            f"underserved segments {brand.target_audience}",
            f"venture capital investment {industry} 2026",
            f"{industry} market growth forecast report",
        ]

    @staticmethod
    def get_synthesis_prompt(signals: list[ExternalSignal], brand: Any) -> str:
        signals_text = ""
        for i, s in enumerate(signals[:15], 1):
            facts = "; ".join(s.extracted_facts[:3]) if s.extracted_facts else "(no facts extracted)"
            signals_text += f"{i}. [{s.source_url[:60]}] {facts}\n"

        return f"""\
You are a market analyst conducting a Market Breakdown for {brand.display_name}.

Business: {brand.one_liner}
Target audience: {brand.target_audience}

## External Data Collected
{signals_text}

## Analysis Required
Using ONLY the external data above, produce:

1. **TAM** — Total Addressable Market estimate with source citation
2. **SAM** — Serviceable Addressable Market given this positioning
3. **SOM** — Serviceable Obtainable Market in next 12 months
4. **Demand Trends** — 3-5 trends with direction (growing/declining/emerging)
5. **Underserved Opportunities** — 2-3 specific gaps existing players are missing
6. **Capital Flows** — Investment trends, funding, M&A in the space

Return as JSON (no markdown fences):
{{
  "tam": {{"estimate": "$X", "source": "...", "confidence": "high|medium|low"}},
  "sam": {{"estimate": "$X", "rationale": "..."}},
  "som": {{"estimate": "$X", "timeframe": "12 months", "rationale": "..."}},
  "demand_trends": [{{"trend": "...", "direction": "growing|declining|emerging", "evidence": "..."}}],
  "underserved_opportunities": [{{"segment": "...", "gap": "...", "potential": "..."}}],
  "capital_flows": [{{"event": "...", "amount": "", "relevance": "..."}}]
}}

Be conservative. Flag low-confidence data. Do not speculate beyond what the data supports."""

    @staticmethod
    def get_output_schema() -> type:
        return MarketBreakdownOutput

    @staticmethod
    def _extract_industry(brand: Any) -> str:
        """Extract industry keywords from brand one_liner."""
        text = brand.one_liner.lower()
        # Remove common words, keep nouns
        for w in ("is", "a", "an", "the", "and", "or", "for", "with", "that", "from"):
            text = text.replace(f" {w} ", " ")
        words = text.split()[:6]
        return " ".join(words)
