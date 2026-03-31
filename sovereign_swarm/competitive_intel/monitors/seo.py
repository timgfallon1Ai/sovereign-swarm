"""SEO monitoring for competitor keyword rankings and domain analysis."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import structlog

logger = structlog.get_logger()


@dataclass
class SEOSnapshot:
    """Point-in-time SEO data for a competitor."""

    domain: str
    captured_at: datetime
    estimated_domain_authority: float = 0.0  # 0-100 heuristic
    estimated_monthly_traffic: str = ""
    top_keywords: list[str] = field(default_factory=list)
    keyword_rankings: dict[str, int] = field(default_factory=dict)  # keyword -> position
    backlink_count_estimate: int = 0
    content_pages_indexed: int = 0


class SEOMonitor:
    """Tracks competitor keyword rankings and domain authority.

    Uses heuristic analysis of search result patterns. Phase A relies
    on stored/manual data; Phase B will integrate with SEO data APIs.
    """

    def __init__(self) -> None:
        self._history: dict[str, list[SEOSnapshot]] = {}  # domain -> snapshots

    async def capture_snapshot(
        self,
        domain: str,
        keywords: list[str] | None = None,
        manual_data: dict[str, Any] | None = None,
    ) -> SEOSnapshot:
        """Capture an SEO snapshot for a domain.

        Phase A: uses manual data if provided, otherwise generates
        heuristic estimates.
        """
        data = manual_data or {}

        snapshot = SEOSnapshot(
            domain=domain,
            captured_at=datetime.now(),
            estimated_domain_authority=data.get("domain_authority", self._estimate_da(domain)),
            estimated_monthly_traffic=data.get("monthly_traffic", "unknown"),
            top_keywords=data.get("top_keywords", keywords or []),
            keyword_rankings=data.get("keyword_rankings", {}),
            backlink_count_estimate=data.get("backlinks", 0),
            content_pages_indexed=data.get("pages_indexed", 0),
        )

        self._history.setdefault(domain, []).append(snapshot)
        return snapshot

    async def compare_domains(
        self, domains: list[str]
    ) -> dict[str, Any]:
        """Compare SEO metrics across multiple domains."""
        comparison: list[dict[str, Any]] = []

        for domain in domains:
            history = self._history.get(domain, [])
            if history:
                latest = history[-1]
                comparison.append({
                    "domain": domain,
                    "domain_authority": latest.estimated_domain_authority,
                    "monthly_traffic": latest.estimated_monthly_traffic,
                    "top_keywords": latest.top_keywords[:5],
                    "backlinks": latest.backlink_count_estimate,
                    "pages_indexed": latest.content_pages_indexed,
                    "last_captured": latest.captured_at.isoformat(),
                })
            else:
                comparison.append({
                    "domain": domain,
                    "domain_authority": 0,
                    "monthly_traffic": "no data",
                    "top_keywords": [],
                    "backlinks": 0,
                    "pages_indexed": 0,
                    "last_captured": "never",
                })

        return {"domains": comparison}

    async def track_keyword_positions(
        self, domain: str, keywords: list[str]
    ) -> dict[str, list[dict[str, Any]]]:
        """Track keyword position changes over time for a domain."""
        history = self._history.get(domain, [])
        tracking: dict[str, list[dict[str, Any]]] = {}

        for kw in keywords:
            positions = []
            for snapshot in history:
                pos = snapshot.keyword_rankings.get(kw)
                if pos is not None:
                    positions.append({
                        "date": snapshot.captured_at.isoformat(),
                        "position": pos,
                    })
            tracking[kw] = positions

        return tracking

    def format_comparison_markdown(self, comparison: dict[str, Any]) -> str:
        """Format domain comparison as markdown."""
        domains = comparison.get("domains", [])
        if not domains:
            return "## SEO Comparison\n\nNo domain data available."

        lines = [
            "## SEO Domain Comparison\n",
            "| Domain | DA | Traffic | Backlinks | Pages |",
            "|--------|----|---------|-----------|-------|",
        ]
        for d in domains:
            lines.append(
                f"| {d['domain']} "
                f"| {d['domain_authority']:.0f} "
                f"| {d['monthly_traffic']} "
                f"| {d['backlinks']:,} "
                f"| {d['pages_indexed']:,} |"
            )

        return "\n".join(lines)

    @staticmethod
    def _estimate_da(domain: str) -> float:
        """Rough heuristic DA estimate based on domain characteristics.

        This is a placeholder; real DA requires Moz/Ahrefs API data.
        """
        # Simple heuristic: shorter domains tend to be older/more authoritative
        length_factor = max(0, 50 - len(domain))
        tld_bonus = 10 if domain.endswith(".com") else 5
        return min(float(length_factor + tld_bonus), 100.0)
