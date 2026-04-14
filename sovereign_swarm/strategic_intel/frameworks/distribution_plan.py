"""Framework 4: Distribution Domination Plan (Tier 1 — weekly).

30-day distribution plan: channels, formats, calendar, organic/paid split.
"""

from __future__ import annotations

from typing import Any

from sovereign_swarm.strategic_intel.models import (
    DistributionPlanOutput,
    ExternalSignal,
    FrameworkTier,
)


class DistributionPlanFramework:
    name = "distribution_plan"
    tier = FrameworkTier.AUTOMATED
    description = "30-day distribution plan with channels, formats, calendar"

    @staticmethod
    def get_search_queries(tenant: str, brand: Any) -> list[str]:
        audience = brand.target_audience[:80]
        return [
            f"{audience} where they spend time online",
            f"{audience} marketing channels ROI best",
            f"{brand.display_name} competitors advertising strategy",
            f"{audience} acquisition channels cost efficiency 2026",
            f"small business distribution strategy {audience}",
            f"{audience} cold email vs content marketing vs paid ads",
        ]

    @staticmethod
    def get_synthesis_prompt(signals: list[ExternalSignal], brand: Any) -> str:
        signals_text = ""
        for i, s in enumerate(signals[:15], 1):
            facts = "; ".join(s.extracted_facts[:3]) if s.extracted_facts else "(no facts)"
            signals_text += f"{i}. [{s.source_url[:60]}] {facts}\n"

        return f"""\
Act as a senior growth strategist for {brand.display_name}.

Business: {brand.one_liner}
Audience: {brand.target_audience}
Budget context: small business, under $5K/month marketing budget

## External Data
{signals_text}

## Task
Build a realistic 30-day distribution plan:

1. **Top 5 acquisition channels** ranked by cost-efficiency for this audience
2. **Content format per channel**: one specific format that works on each
3. **Weekly execution calendar**: what happens in weeks 1, 2, 3, 4
4. **Organic vs paid split**: recommended % allocation and rationale
5. **Leverage plays**: 2-3 tactics that multiply reach without proportional effort

Skip tactics requiring a large team or $50K+ budget.

Return as JSON (no markdown fences):
{{
  "top_channels": [{{"channel": "...", "format": "...", "cost_efficiency_rank": 1, "rationale": "..."}}],
  "weekly_calendar": {{
    "week1": ["action1", "action2"],
    "week2": ["action1", "action2"],
    "week3": ["action1", "action2"],
    "week4": ["action1", "action2"]
  }},
  "organic_paid_split": {{"organic_pct": 70, "paid_pct": 30, "rationale": "..."}},
  "leverage_plays": ["play1", "play2", "play3"]
}}"""

    @staticmethod
    def get_output_schema() -> type:
        return DistributionPlanOutput
