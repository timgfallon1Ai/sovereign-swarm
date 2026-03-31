"""Regulatory monitoring -- tracks changes from Fed, CFTC, SEC, and other agencies."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import structlog

from sovereign_swarm.legal.models import RegulatoryAlert

logger = structlog.get_logger()

# RSS feed sources for regulatory monitoring (Phase A: metadata only, actual fetching in Phase B)
_REGULATORY_SOURCES: list[dict[str, str]] = [
    {
        "agency": "CFTC",
        "name": "CFTC Press Releases",
        "url": "https://www.cftc.gov/PressRoom/PressReleases/rss.xml",
        "relevance": "Kalshi prediction markets, event contracts",
    },
    {
        "agency": "SEC",
        "name": "SEC Press Releases",
        "url": "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&type=&dateb=&owner=include&count=40&search_text=&action=getcompany",
        "relevance": "Equities trading, reporting requirements",
    },
    {
        "agency": "Federal Reserve",
        "name": "Fed Press Releases",
        "url": "https://www.federalreserve.gov/feeds/press_all.xml",
        "relevance": "Interest rates, monetary policy, macro impact",
    },
    {
        "agency": "FTC",
        "name": "FTC AI Guidance",
        "url": "https://www.ftc.gov/rss/press-release.xml",
        "relevance": "AI regulations, consumer protection, advertising",
    },
    {
        "agency": "State",
        "name": "Texas Business Regulations",
        "url": "",
        "relevance": "GBB and Sovereign Mind operations",
    },
]


class RegulatoryMonitor:
    """Monitors for regulatory changes relevant to Tim's operations."""

    def __init__(self) -> None:
        self._alerts: list[RegulatoryAlert] = []
        self._last_check: datetime | None = None

    async def check_for_updates(self) -> list[RegulatoryAlert]:
        """Check all regulatory sources for new announcements.

        Phase A: returns stub alerts demonstrating the monitoring framework.
        Phase B: fetches actual RSS feeds and parses announcements.
        """
        logger.info("regulatory.checking_updates")
        self._last_check = datetime.utcnow()

        # Phase A: demonstrate the framework with stub alerts
        new_alerts = self._generate_stub_alerts()
        self._alerts.extend(new_alerts)

        logger.info("regulatory.check_complete", new_alerts=len(new_alerts))
        return new_alerts

    def get_all_alerts(self) -> list[RegulatoryAlert]:
        """Return all stored regulatory alerts."""
        return self._alerts

    def get_alerts_by_impact(self, impact: str) -> list[RegulatoryAlert]:
        """Filter alerts by impact level (low, medium, high)."""
        return [a for a in self._alerts if a.impact == impact]

    def get_sources(self) -> list[dict[str, str]]:
        """Return the list of monitored regulatory sources."""
        return _REGULATORY_SOURCES

    @staticmethod
    def _generate_stub_alerts() -> list[RegulatoryAlert]:
        """Generate stub alerts for Phase A demonstration."""
        return [
            RegulatoryAlert(
                regulation="CFTC Event Contracts Rule",
                change_description=(
                    "CFTC reviewing event contract exchange regulations. "
                    "Potential impact on Kalshi position limits and reporting."
                ),
                impact="medium",
                action_required="Monitor CFTC docket for final rulemaking",
                source_url="https://www.cftc.gov",
            ),
            RegulatoryAlert(
                regulation="SEC AI Disclosure Requirements",
                change_description=(
                    "SEC considering new disclosure requirements for AI-driven "
                    "trading systems and automated investment advisors."
                ),
                impact="low",
                action_required="Review when final rule is published",
                source_url="https://www.sec.gov",
            ),
            RegulatoryAlert(
                regulation="Texas Data Privacy Act",
                change_description=(
                    "Texas TDPSA enforcement guidance updated. "
                    "Applies to businesses processing personal data of Texas residents."
                ),
                impact="medium",
                action_required="Review data processing practices for TDPSA compliance",
                source_url="https://capitol.texas.gov",
            ),
        ]

    def clear_alerts(self) -> int:
        """Clear all stored alerts. Returns the number cleared."""
        count = len(self._alerts)
        self._alerts.clear()
        return count
