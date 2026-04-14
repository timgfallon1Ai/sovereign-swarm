"""Framework 6: Competitor Weakness Map (Tier 2 — on-demand).

Top 5 competitors: strengths, weaknesses, ignored audiences, gap analysis.
"""

from __future__ import annotations

from typing import Any

from sovereign_swarm.strategic_intel.models import (
    CompetitorMapOutput,
    ExternalSignal,
    FrameworkTier,
)


class CompetitorMapFramework:
    name = "competitor_map"
    tier = FrameworkTier.ON_DEMAND
    description = "Top 5 competitor analysis with gap analysis and positioning"

    @staticmethod
    def get_search_queries(tenant: str, brand: Any) -> list[str]:
        return [
            f"{brand.display_name} competitors alternatives",
            f"{brand.display_name} vs comparison review",
            f"{brand.target_audience} best solutions providers ranked",
            f"{brand.display_name} competitor weaknesses complaints",
            f"{brand.target_audience} underserved audience segments",
            f"{brand.display_name} industry competitive landscape 2026",
        ]

    @staticmethod
    def get_synthesis_prompt(signals: list[ExternalSignal], brand: Any) -> str:
        signals_text = ""
        for i, s in enumerate(signals[:15], 1):
            facts = "; ".join(s.extracted_facts[:3]) if s.extracted_facts else "(no facts)"
            signals_text += f"{i}. [{s.source_url[:60]}] {facts}\n"

        return f"""\
You are a competitive strategist analyzing {brand.display_name}'s landscape.

Business: {brand.one_liner}
Target audience: {brand.target_audience}

## External Intelligence
{signals_text}

## Task
Map the top 5 competitors based on the external data:

For EACH competitor:
1. Name & URL
2. Strengths (2-3 items)
3. Weaknesses (2-3 items)
4. Ignored audiences they're neglecting
5. Gap analysis vs {brand.display_name}
6. Positioning angle for {brand.display_name} against this competitor

Then produce:
- A positioning statement for {brand.display_name}
- Key differentiators (3-5)
- The single biggest competitive vulnerability

Return as JSON (no markdown fences):
{{
  "competitors": [
    {{
      "name": "...",
      "url": "...",
      "strengths": ["..."],
      "weaknesses": ["..."],
      "ignored_audiences": ["..."],
      "gap_analysis": "...",
      "positioning_angle": "..."
    }}
  ],
  "positioning_statement": "...",
  "key_differentiators": ["..."],
  "biggest_vulnerability": "..."
}}

Base ALL findings on collected external data. Do not invent competitors."""

    @staticmethod
    def get_output_schema() -> type:
        return CompetitorMapOutput
