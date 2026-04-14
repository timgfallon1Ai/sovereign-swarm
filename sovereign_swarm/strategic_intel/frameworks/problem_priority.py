"""Framework 2: Problem Prioritization Engine (Tier 1 — weekly).

Score top 10 industry problems on Urgency x WTP x Growth Trajectory.
"""

from __future__ import annotations

from typing import Any

from sovereign_swarm.strategic_intel.models import (
    ExternalSignal,
    FrameworkTier,
    ProblemPriorityOutput,
)


class ProblemPriorityFramework:
    name = "problem_priority"
    tier = FrameworkTier.AUTOMATED
    description = "Score industry problems on Urgency x WTP x Growth Trajectory"

    @staticmethod
    def get_search_queries(tenant: str, brand: Any) -> list[str]:
        audience = brand.target_audience[:100]
        return [
            f"{audience} biggest problems challenges 2026",
            f"{audience} complaints pain points reddit forum",
            f"{audience} willingness to pay solutions survey",
            f"{audience} industry problems rising fast",
            f"{brand.display_name} customer complaints reviews",
            f"{audience} frustrations unmet needs",
        ]

    @staticmethod
    def get_synthesis_prompt(signals: list[ExternalSignal], brand: Any) -> str:
        signals_text = ""
        for i, s in enumerate(signals[:15], 1):
            facts = "; ".join(s.extracted_facts[:3]) if s.extracted_facts else "(no facts)"
            signals_text += f"{i}. [{s.source_url[:60]}] {facts}\n"

        return f"""\
You are a problem analyst for {brand.display_name}'s market.

Business: {brand.one_liner}
Target audience: {brand.target_audience}

## External Data
{signals_text}

## Task
List the top 10 problems in this industry. For each, score on:
- Urgency (1-10): how painful/time-sensitive right now
- Willingness to pay (1-10): how likely buyers spend money to solve today
- Growth trajectory: "rising_fast", "stable", or "declining"
- Complaint signal: true/false — does this surface in reviews, forums, sales calls

Sort by combined Urgency + WTP score, highest first.

Return as JSON (no markdown fences):
{{
  "problems": [
    {{
      "problem": "...",
      "urgency": 8,
      "willingness_to_pay": 7,
      "growth_trajectory": "rising_fast",
      "complaint_signal": true,
      "combined_score": 15,
      "rationale": "..."
    }}
  ]
}}"""

    @staticmethod
    def get_output_schema() -> type:
        return ProblemPriorityOutput
