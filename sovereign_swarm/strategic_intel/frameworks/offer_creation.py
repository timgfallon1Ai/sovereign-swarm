"""Framework 3: Offer Creation Framework (Tier 2 — on-demand).

Landing page structure: headline, ICP, value prop, pricing tiers, guarantee.
"""

from __future__ import annotations

from typing import Any

from sovereign_swarm.strategic_intel.models import (
    ExternalSignal,
    FrameworkTier,
    OfferCreationOutput,
)


class OfferCreationFramework:
    name = "offer_creation"
    tier = FrameworkTier.ON_DEMAND
    description = "High-converting offer structure with pricing tiers and guarantee"

    @staticmethod
    def get_search_queries(tenant: str, brand: Any) -> list[str]:
        audience = brand.target_audience[:80]
        return [
            f"{audience} pricing models best practices",
            f"{brand.display_name} competitors pricing comparison",
            f"{audience} ideal solution features survey",
            f"{audience} buying decision factors",
            f"{brand.display_name} industry offer structures",
            f"{audience} risk reversal guarantee examples",
        ]

    @staticmethod
    def get_synthesis_prompt(signals: list[ExternalSignal], brand: Any) -> str:
        signals_text = ""
        for i, s in enumerate(signals[:15], 1):
            facts = "; ".join(s.extracted_facts[:3]) if s.extracted_facts else "(no facts)"
            signals_text += f"{i}. [{s.source_url[:60]}] {facts}\n"

        return f"""\
Create a high-converting offer for {brand.display_name}.

Business: {brand.one_liner}
Audience: {brand.target_audience}

## External Data
{signals_text}

## Task
Structure like a landing page with these sections:

1. **Headline**: one bold, benefit-driven statement
2. **ICP**: who this is for (role, situation, pain level)
3. **Value proposition**: the core transformation in one sentence
4. **Offer components**: what's included (deliverables, bonuses, format)
5. **Pricing tiers**: name, price, and what changes at each tier (low/mid/premium)
6. **Guarantee**: specific risk-reversal language
7. **Competitive edge**: 3 reasons this beats alternatives

Keep each section tight. No filler. Write as if it goes on a real landing page.

Return as JSON (no markdown fences):
{{
  "offer": {{
    "headline": "...",
    "icp": "...",
    "value_proposition": "...",
    "offer_components": ["..."],
    "pricing_tiers": [{{"name": "...", "price": "...", "includes": "..."}}],
    "guarantee": "...",
    "competitive_edge": ["..."]
  }}
}}"""

    @staticmethod
    def get_output_schema() -> type:
        return OfferCreationOutput
