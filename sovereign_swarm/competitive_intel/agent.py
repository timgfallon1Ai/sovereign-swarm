"""CompetitiveIntelAgent -- competitive intelligence for the swarm."""

from __future__ import annotations

import uuid
from typing import Any

import structlog

from sovereign_swarm.competitive_intel.models import (
    Competitor,
    CompetitorChange,
    MarketPosition,
)
from sovereign_swarm.protocol.swarm_agent import (
    SwarmAgent,
    SwarmAgentCard,
    SwarmAgentRequest,
    SwarmAgentResponse,
)

logger = structlog.get_logger()


class CompetitiveIntelAgent(SwarmAgent):
    """Competitive intelligence agent.

    Monitors competitors, analyzes market positioning, compares pricing,
    tracks website/SEO/social changes, and synthesizes actionable intelligence.
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._config = config or {}
        self._website_monitor = None
        self._seo_monitor = None
        self._social_monitor = None
        self._analyzer = None
        self._anthropic = None
        # In-memory competitor store
        self._competitors: dict[str, Competitor] = {}
        self._changes: list[CompetitorChange] = []

    @property
    def card(self) -> SwarmAgentCard:
        return SwarmAgentCard(
            name="competitive_intel",
            description=(
                "Competitive intelligence agent -- monitors competitors, "
                "analyzes market positioning, compares pricing and SEO, "
                "tracks changes, and produces actionable intelligence."
            ),
            version="0.1.0",
            domains=["competitive", "intelligence", "market", "competitors"],
            supported_intents=[
                "competitor_analysis",
                "pricing_comparison",
                "seo_comparison",
                "market_position",
                "track_changes",
            ],
            capabilities=[
                "competitor_analysis",
                "pricing_comparison",
                "seo_comparison",
                "market_position",
                "track_changes",
            ],
        )

    # ------------------------------------------------------------------
    # Core execute
    # ------------------------------------------------------------------

    async def execute(self, request: SwarmAgentRequest) -> SwarmAgentResponse:
        """Route a competitive intel task to the appropriate handler."""
        task = request.task.lower()
        params = request.parameters or request.context or {}

        try:
            if any(kw in task for kw in ("swot", "analysis", "analyze competitor")):
                result = await self._handle_competitor_analysis(params)
            elif any(kw in task for kw in ("pricing", "price", "cost comparison")):
                result = await self._handle_pricing_comparison(params)
            elif any(kw in task for kw in ("seo", "keyword", "ranking", "domain")):
                result = await self._handle_seo_comparison(params)
            elif any(kw in task for kw in ("market", "position", "landscape")):
                result = await self._handle_market_position(params)
            elif any(kw in task for kw in ("track", "monitor", "change", "watch")):
                result = await self._handle_track_changes(params)
            elif any(kw in task for kw in ("add competitor", "register", "new competitor")):
                result = await self._handle_add_competitor(params)
            elif any(kw in task for kw in ("list", "competitors", "all")):
                result = await self._handle_list_competitors()
            else:
                result = await self._handle_list_competitors()

            return SwarmAgentResponse(
                agent_name=self.card.name,
                status="success",
                output=result.get("markdown", str(result)),
                data=result,
                confidence=result.get("confidence", 0.7),
            )
        except Exception as e:
            logger.error("competitive_intel.execute_failed", error=str(e))
            return SwarmAgentResponse(
                agent_name=self.card.name,
                status="error",
                error=str(e),
            )

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------

    async def _handle_add_competitor(self, params: dict) -> dict:
        """Register a new competitor for tracking."""
        comp = Competitor(
            id=f"comp_{uuid.uuid4().hex[:8]}",
            name=params.get("name", "Unknown"),
            url=params.get("url", ""),
            description=params.get("description", ""),
            products=params.get("products", []),
            pricing=params.get("pricing", {}),
            strengths=params.get("strengths", []),
            weaknesses=params.get("weaknesses", []),
        )
        self._competitors[comp.id] = comp

        md = (
            f"## Competitor Registered: {comp.name}\n\n"
            f"**ID:** {comp.id}\n"
            f"**URL:** {comp.url}\n"
            f"**Products:** {', '.join(comp.products) or 'N/A'}\n"
        )
        return {"markdown": md, "competitor_id": comp.id, "confidence": 0.9}

    async def _handle_competitor_analysis(self, params: dict) -> dict:
        """Run SWOT analysis on a competitor."""
        analyzer = self._get_analyzer()
        comp_id = params.get("competitor_id", "")
        comp = self._competitors.get(comp_id)

        if not comp:
            # Build from params
            comp = Competitor(
                name=params.get("name", "Competitor"),
                url=params.get("url", ""),
                strengths=params.get("strengths", []),
                weaknesses=params.get("weaknesses", []),
                products=params.get("products", []),
            )

        result = await analyzer.swot_analysis(comp)
        result["confidence"] = 0.7
        return result

    async def _handle_pricing_comparison(self, params: dict) -> dict:
        """Compare pricing across competitors."""
        analyzer = self._get_analyzer()
        comp_ids = params.get("competitor_ids", [])
        competitors = [
            self._competitors[cid]
            for cid in comp_ids
            if cid in self._competitors
        ]
        if not competitors:
            competitors = list(self._competitors.values())

        our_pricing = params.get("our_pricing", {})
        result = await analyzer.pricing_comparison(competitors, our_pricing)
        result["confidence"] = 0.7
        return result

    async def _handle_seo_comparison(self, params: dict) -> dict:
        """Compare SEO metrics across competitor domains."""
        seo = self._get_seo_monitor()
        domains = params.get("domains", [])

        if not domains:
            domains = [c.url for c in self._competitors.values() if c.url]

        if not domains:
            return {
                "markdown": "## SEO Comparison\n\nNo domains to compare. Add competitors first.",
                "confidence": 0.5,
            }

        comparison = await seo.compare_domains(domains)
        md = seo.format_comparison_markdown(comparison)

        return {"markdown": md, "comparison": comparison, "confidence": 0.6}

    async def _handle_market_position(self, params: dict) -> dict:
        """Analyze market positioning."""
        analyzer = self._get_analyzer()
        competitors = list(self._competitors.values())

        if not competitors:
            return {
                "markdown": (
                    "## Market Position\n\n"
                    "No competitors tracked. Use 'add competitor' to start."
                ),
                "confidence": 0.5,
            }

        result = await analyzer.competitive_summary(competitors)
        result["confidence"] = 0.65
        return result

    async def _handle_track_changes(self, params: dict) -> dict:
        """Check for changes on competitor websites."""
        monitor = self._get_website_monitor()
        url = params.get("url", "")
        comp_id = params.get("competitor_id", "")
        comp_name = params.get("competitor_name", "")

        if not url and comp_id:
            comp = self._competitors.get(comp_id)
            if comp:
                url = comp.url
                comp_name = comp.name

        if not url:
            return {
                "markdown": "## Change Tracking\n\nNo URL provided to monitor.",
                "confidence": 0.5,
            }

        change = await monitor.check_for_changes(url, comp_id, comp_name)
        if change:
            self._changes.append(change)
            md = (
                f"## Change Detected: {comp_name or url}\n\n"
                f"**Type:** {change.change_type.value}\n"
                f"**Significance:** {change.significance}\n"
                f"**Details:** {change.notes}\n"
                f"**Detected:** {change.detected_at.isoformat()}\n"
            )
        else:
            md = f"## No Changes Detected\n\n**URL:** {url}\n"
            history = monitor.get_snapshot_history(url)
            md += f"**Snapshots stored:** {len(history)}\n"

        return {"markdown": md, "confidence": 0.7}

    async def _handle_list_competitors(self) -> dict:
        """List all tracked competitors."""
        if not self._competitors:
            return {
                "markdown": (
                    "## Tracked Competitors\n\n"
                    "No competitors registered. Use 'add competitor' to begin tracking."
                ),
                "confidence": 0.9,
            }

        md = f"## Tracked Competitors ({len(self._competitors)})\n\n"
        md += "| Name | URL | Products | Last Analyzed |\n"
        md += "|------|-----|----------|---------------|\n"
        for comp in self._competitors.values():
            products = ", ".join(comp.products[:3]) or "N/A"
            last = comp.last_analyzed.isoformat() if comp.last_analyzed else "never"
            md += f"| {comp.name} | {comp.url} | {products} | {last} |\n"

        return {"markdown": md, "count": len(self._competitors), "confidence": 0.9}

    # ------------------------------------------------------------------
    # Lazy init
    # ------------------------------------------------------------------

    def _get_anthropic(self):
        if self._anthropic is None:
            try:
                import anthropic

                self._anthropic = anthropic.AsyncAnthropic()
            except Exception:
                self._anthropic = None
        return self._anthropic

    def _get_website_monitor(self):
        if self._website_monitor is None:
            from sovereign_swarm.competitive_intel.monitors.website import WebsiteMonitor

            self._website_monitor = WebsiteMonitor()
        return self._website_monitor

    def _get_seo_monitor(self):
        if self._seo_monitor is None:
            from sovereign_swarm.competitive_intel.monitors.seo import SEOMonitor

            self._seo_monitor = SEOMonitor()
        return self._seo_monitor

    def _get_social_monitor(self):
        if self._social_monitor is None:
            from sovereign_swarm.competitive_intel.monitors.social import SocialMonitor

            self._social_monitor = SocialMonitor()
        return self._social_monitor

    def _get_analyzer(self):
        if self._analyzer is None:
            from sovereign_swarm.competitive_intel.analyzer import CompetitiveAnalyzer

            self._analyzer = CompetitiveAnalyzer(anthropic_client=self._get_anthropic())
        return self._analyzer
