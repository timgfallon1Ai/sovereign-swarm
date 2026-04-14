"""Framework 7: The Scale System (Tier 2 — on-demand).

12-month phased execution roadmap: stabilize, automate, delegate, scale.
"""

from __future__ import annotations

from typing import Any

from sovereign_swarm.strategic_intel.models import (
    ExternalSignal,
    FrameworkTier,
    ScaleSystemOutput,
)


class ScaleSystemFramework:
    name = "scale_system"
    tier = FrameworkTier.ON_DEMAND
    description = "12-month phased scaling roadmap"

    @staticmethod
    def get_search_queries(tenant: str, brand: Any) -> list[str]:
        audience = brand.target_audience[:80]
        return [
            f"{brand.display_name} industry scaling playbook small business",
            f"automation tools {audience} industry 2026",
            f"small business delegation framework hiring order",
            f"{brand.display_name} industry growth levers",
            f"scaling from $1M to $5M {audience} industry",
            f"{brand.display_name} industry partnerships distribution",
        ]

    @staticmethod
    def get_synthesis_prompt(signals: list[ExternalSignal], brand: Any) -> str:
        signals_text = ""
        for i, s in enumerate(signals[:15], 1):
            facts = "; ".join(s.extracted_facts[:3]) if s.extracted_facts else "(no facts)"
            signals_text += f"{i}. [{s.source_url[:60]}] {facts}\n"

        return f"""\
Give a plan to scale {brand.display_name} within 12 months.

Business: {brand.one_liner}
Audience: {brand.target_audience}

## External Data
{signals_text}

## Task
Structure as a phased execution roadmap:

Phase 1 - Stabilize (Month 1-2): what to systematize and document before scaling
Phase 2 - Automate (Month 3-4): top 3 processes to automate, with specific tool recommendations
Phase 3 - Delegate (Month 5-8): what to hire first, in order, with rough cost per role
Phase 4 - Scale (Month 9-12): the growth lever (channel, product, or partnership) that unlocks the next revenue tier

Also include:
- Top 3 bottlenecks at each phase transition
- One leading metric per phase (not vanity metrics)

Return as JSON (no markdown fences):
{{
  "target_revenue": "$X",
  "timeframe": "12 months",
  "phases": [
    {{
      "name": "Stabilize",
      "months": "1-2",
      "actions": ["..."],
      "bottlenecks": ["..."],
      "leading_metric": "..."
    }}
  ]
}}"""

    @staticmethod
    def get_output_schema() -> type:
        return ScaleSystemOutput
