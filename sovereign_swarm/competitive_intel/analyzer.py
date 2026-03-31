"""Competitive analysis synthesizer for actionable intelligence."""

from __future__ import annotations

from typing import Any

import structlog

from sovereign_swarm.competitive_intel.models import Competitor, MarketPosition, MarketTrend

logger = structlog.get_logger()


class CompetitiveAnalyzer:
    """Synthesizes monitoring data into actionable intelligence.

    Generates SWOT analyses, competitive positioning maps, and pricing
    comparison matrices. Uses Claude API if available for narrative synthesis.
    """

    def __init__(self, anthropic_client: Any | None = None) -> None:
        self._client = anthropic_client

    async def swot_analysis(self, competitor: Competitor) -> dict[str, Any]:
        """Generate a SWOT analysis for a competitor."""
        swot = {
            "competitor": competitor.name,
            "strengths": competitor.strengths or ["[No data -- add strengths]"],
            "weaknesses": competitor.weaknesses or ["[No data -- add weaknesses]"],
            "opportunities": self._identify_opportunities(competitor),
            "threats": self._identify_threats(competitor),
        }

        md = f"## SWOT Analysis: {competitor.name}\n\n"
        md += f"**URL:** {competitor.url}\n\n" if competitor.url else ""

        for section in ["strengths", "weaknesses", "opportunities", "threats"]:
            md += f"### {section.title()}\n"
            for item in swot[section]:
                md += f"- {item}\n"
            md += "\n"

        return {"markdown": md, "swot": swot}

    async def pricing_comparison(
        self, competitors: list[Competitor], our_pricing: dict[str, str] | None = None
    ) -> dict[str, Any]:
        """Generate a pricing comparison matrix."""
        our_pricing = our_pricing or {}

        md = "## Pricing Comparison\n\n"
        # Gather all plan names
        all_plans: set[str] = set()
        for c in competitors:
            all_plans.update(c.pricing.keys())
        if our_pricing:
            all_plans.update(our_pricing.keys())

        if not all_plans:
            md += "No pricing data available for comparison.\n"
            return {"markdown": md, "plans": []}

        plans = sorted(all_plans)

        # Header
        headers = ["Plan"]
        if our_pricing:
            headers.append("Us")
        headers.extend(c.name for c in competitors)

        md += "| " + " | ".join(headers) + " |\n"
        md += "| " + " | ".join("---" for _ in headers) + " |\n"

        for plan in plans:
            row = [plan]
            if our_pricing:
                row.append(our_pricing.get(plan, "N/A"))
            for c in competitors:
                row.append(c.pricing.get(plan, "N/A"))
            md += "| " + " | ".join(row) + " |\n"

        return {"markdown": md, "plans": plans}

    async def market_positioning(
        self,
        market: str,
        our_position: str,
        competitors: list[Competitor],
        market_size: str = "",
    ) -> MarketPosition:
        """Generate a market positioning analysis."""
        position = MarketPosition(
            market=market,
            our_position=our_position,
            competitors=[c.name for c in competitors],
            market_size=market_size,
            trend=MarketTrend.STABLE,
        )
        return position

    async def competitive_summary(
        self, competitors: list[Competitor]
    ) -> dict[str, Any]:
        """Generate a comprehensive competitive landscape summary."""
        if self._client:
            return await self._summary_with_claude(competitors)
        return self._summary_template(competitors)

    async def _summary_with_claude(self, competitors: list[Competitor]) -> dict[str, Any]:
        """Generate narrative summary using Claude."""
        prompt = "Analyze the following competitive landscape:\n\n"
        for c in competitors:
            prompt += f"**{c.name}** ({c.url})\n"
            prompt += f"- Products: {', '.join(c.products)}\n"
            prompt += f"- Strengths: {', '.join(c.strengths)}\n"
            prompt += f"- Weaknesses: {', '.join(c.weaknesses)}\n\n"

        prompt += (
            "Provide a concise competitive analysis covering:\n"
            "1. Key trends across competitors\n"
            "2. Market gaps and opportunities\n"
            "3. Recommended strategic responses\n"
        )

        try:
            response = await self._client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=2048,
                messages=[{"role": "user", "content": prompt}],
            )
            narrative = response.content[0].text

            md = "## Competitive Landscape Summary\n\n"
            md += narrative
            return {"markdown": md, "generated_by": "claude"}
        except Exception as e:
            logger.warning("analyzer.claude_fallback", error=str(e))
            return self._summary_template(competitors)

    def _summary_template(self, competitors: list[Competitor]) -> dict[str, Any]:
        """Template-based competitive summary."""
        md = f"## Competitive Landscape Summary ({len(competitors)} competitors)\n\n"

        md += "| Competitor | Products | Strengths | Weaknesses |\n"
        md += "|-----------|----------|-----------|------------|\n"
        for c in competitors:
            products = ", ".join(c.products[:3]) or "N/A"
            strengths = ", ".join(c.strengths[:2]) or "N/A"
            weaknesses = ", ".join(c.weaknesses[:2]) or "N/A"
            md += f"| {c.name} | {products} | {strengths} | {weaknesses} |\n"

        md += "\n### Key Observations\n"
        md += "- [Identify common strengths across competitors]\n"
        md += "- [Note gaps in competitor offerings]\n"
        md += "- [Highlight differentiation opportunities]\n"

        return {"markdown": md, "generated_by": "template"}

    @staticmethod
    def _identify_opportunities(competitor: Competitor) -> list[str]:
        """Identify opportunities based on competitor weaknesses."""
        opportunities = []
        for weakness in competitor.weaknesses:
            opportunities.append(f"Capitalize on competitor gap: {weakness}")
        if not opportunities:
            opportunities.append("[Analyze competitor weaknesses to identify opportunities]")
        return opportunities[:5]

    @staticmethod
    def _identify_threats(competitor: Competitor) -> list[str]:
        """Identify threats based on competitor strengths."""
        threats = []
        for strength in competitor.strengths:
            threats.append(f"Competitive pressure from: {strength}")
        if not threats:
            threats.append("[Monitor competitor strengths for emerging threats]")
        return threats[:5]
