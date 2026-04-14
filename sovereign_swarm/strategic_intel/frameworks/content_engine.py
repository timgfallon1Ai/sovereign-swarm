"""Framework 5: Viral Content Engine (Tier 1 — weekly).

Hook bank, content format matrix, shareability audit, weekly system.
"""

from __future__ import annotations

from typing import Any

from sovereign_swarm.strategic_intel.models import (
    ContentEngineOutput,
    ExternalSignal,
    FrameworkTier,
)


class ContentEngineFramework:
    name = "content_engine"
    tier = FrameworkTier.AUTOMATED
    description = "Hook bank, content format matrix, shareability audit"

    @staticmethod
    def get_search_queries(tenant: str, brand: Any) -> list[str]:
        audience = brand.target_audience[:80]
        return [
            f"{audience} viral content examples 2026",
            f"{brand.display_name} competitors social media content strategy",
            f"trending topics {audience} industry",
            f"{audience} best performing content formats",
            f"{audience} content hooks high engagement",
            f"{brand.display_name} industry thought leadership content",
        ]

    @staticmethod
    def get_synthesis_prompt(signals: list[ExternalSignal], brand: Any) -> str:
        signals_text = ""
        for i, s in enumerate(signals[:15], 1):
            facts = "; ".join(s.extracted_facts[:3]) if s.extracted_facts else "(no facts)"
            signals_text += f"{i}. [{s.source_url[:60]}] {facts}\n"

        tone = ", ".join(brand.tone_keywords[:3])

        return f"""\
You are a content strategist for {brand.display_name}.

Business: {brand.one_liner}
Audience: {brand.target_audience}
Brand voice: {tone}

## External Data
{signals_text}

## Task
Create a viral content strategy with:

1. **Hook bank**: 10 high-converting hooks using emotional triggers \
(fear of missing out, social status, curiosity, controversy). \
Write in the voice of this niche, not generic marketing language.

2. **Content format matrix**: 6-8 formats across 3+ platforms:
| Format | Platform | Ideal length | Why it spreads | Example title |

3. **Shareability audit**: For each format, one sentence answering \
"What makes someone forward/repost this?"

4. **Weekly system**: Template showing posts per week, which formats, \
and rotation to avoid burnout.

Return as JSON (no markdown fences):
{{
  "hooks": [{{"hook": "...", "emotional_trigger": "fomo|social_status|curiosity|controversy"}}],
  "format_matrix": [{{"format": "...", "platform": "...", "ideal_length": "...", "why_it_spreads": "...", "example_title": "..."}}],
  "shareability_audit": [{{"format": "...", "reason": "..."}}],
  "weekly_system": {{"posts_per_week": 5, "schedule": {{"mon": "...", "wed": "...", "fri": "..."}}, "rotation_notes": "..."}}
}}"""

    @staticmethod
    def get_output_schema() -> type:
        return ContentEngineOutput
