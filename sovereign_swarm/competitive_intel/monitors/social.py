"""Social media monitoring for competitor activity tracking.

Phase A: stub implementation with manual data ingestion.
Phase B: integrate with social media APIs (Twitter/X, Instagram, etc.).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import structlog

logger = structlog.get_logger()


@dataclass
class SocialActivity:
    """A summary of social media activity for a competitor."""

    competitor_name: str
    platform: str
    follower_count: int = 0
    posts_last_30_days: int = 0
    avg_engagement_rate: float = 0.0  # percentage
    top_content_themes: list[str] = field(default_factory=list)
    posting_frequency: str = ""  # e.g., "3x/week"
    captured_at: datetime = field(default_factory=lambda: datetime.now())


class SocialMonitor:
    """Tracks competitor social media activity.

    Phase A: accepts manual data input for competitor social metrics.
    Phase B: will integrate with platform APIs for automated tracking.
    """

    def __init__(self) -> None:
        self._activities: dict[str, list[SocialActivity]] = {}  # competitor -> history

    async def record_activity(
        self,
        competitor_name: str,
        platform: str,
        data: dict[str, Any],
    ) -> SocialActivity:
        """Record social media activity data (manual input for Phase A)."""
        activity = SocialActivity(
            competitor_name=competitor_name,
            platform=platform,
            follower_count=data.get("followers", 0),
            posts_last_30_days=data.get("posts_30d", 0),
            avg_engagement_rate=data.get("engagement_rate", 0.0),
            top_content_themes=data.get("themes", []),
            posting_frequency=data.get("frequency", ""),
        )

        key = f"{competitor_name}:{platform}"
        self._activities.setdefault(key, []).append(activity)

        logger.info(
            "social_monitor.recorded",
            competitor=competitor_name,
            platform=platform,
        )
        return activity

    async def get_competitor_summary(
        self, competitor_name: str
    ) -> list[SocialActivity]:
        """Get latest social activity across all platforms for a competitor."""
        results: list[SocialActivity] = []
        for key, history in self._activities.items():
            if key.startswith(f"{competitor_name}:") and history:
                results.append(history[-1])
        return results

    async def compare_social_presence(
        self, competitor_names: list[str], platform: str = ""
    ) -> list[dict[str, Any]]:
        """Compare social presence across competitors."""
        comparison: list[dict[str, Any]] = []

        for name in competitor_names:
            summaries = await self.get_competitor_summary(name)
            if platform:
                summaries = [s for s in summaries if s.platform == platform]

            total_followers = sum(s.follower_count for s in summaries)
            avg_engagement = (
                sum(s.avg_engagement_rate for s in summaries) / max(len(summaries), 1)
            )

            comparison.append({
                "competitor": name,
                "platforms_tracked": len(summaries),
                "total_followers": total_followers,
                "avg_engagement_rate": round(avg_engagement, 2),
                "platforms": [
                    {
                        "platform": s.platform,
                        "followers": s.follower_count,
                        "engagement": s.avg_engagement_rate,
                        "frequency": s.posting_frequency,
                    }
                    for s in summaries
                ],
            })

        return comparison

    def format_comparison_markdown(self, comparison: list[dict[str, Any]]) -> str:
        """Format social comparison as markdown."""
        if not comparison:
            return "## Social Media Comparison\n\nNo data available."

        lines = [
            "## Social Media Comparison\n",
            "| Competitor | Platforms | Total Followers | Avg Engagement |",
            "|-----------|-----------|-----------------|----------------|",
        ]
        for c in comparison:
            lines.append(
                f"| {c['competitor']} "
                f"| {c['platforms_tracked']} "
                f"| {c['total_followers']:,} "
                f"| {c['avg_engagement_rate']:.1f}% |"
            )

        return "\n".join(lines)
