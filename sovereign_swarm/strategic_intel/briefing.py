"""WeeklyBriefGenerator — produces delta-aware strategic briefings.

Aggregates gap results across frameworks, diffs against prior week,
ranks recommendations, and renders a human-readable markdown briefing.
"""

from __future__ import annotations

import json
import structlog
from datetime import datetime
from pathlib import Path
from typing import Any

from sovereign_swarm.strategic_intel.gap_detector import GapDetector
from sovereign_swarm.strategic_intel.models import (
    FrameworkResult,
    Gap,
    GapClassification,
    WeeklyBriefing,
)

logger = structlog.get_logger()

_CLASSIFICATION_PRIORITY = {
    GapClassification.BLIND_SPOT: 0,
    GapClassification.THREAT: 1,
    GapClassification.OPPORTUNITY: 2,
    GapClassification.CONFIRMED: 3,
}


class WeeklyBriefGenerator:
    """Generates weekly strategic intelligence briefings with delta analysis."""

    def __init__(self, data_dir: str | Path = "data/strategic_intel") -> None:
        self._data_dir = Path(str(data_dir)).expanduser()

    async def generate(
        self,
        tenant: str,
        framework_results: list[FrameworkResult],
        prior_briefing: WeeklyBriefing | None = None,
    ) -> WeeklyBriefing:
        """Generate a weekly briefing with delta analysis."""
        # Load prior if not provided
        if prior_briefing is None:
            prior_briefing = self._load_prior(tenant)

        # Aggregate all gaps
        all_gaps = []
        for fr in framework_results:
            all_gaps.extend(fr.gaps)

        # Sort by classification priority then severity
        all_gaps.sort(
            key=lambda g: (
                _CLASSIFICATION_PRIORITY.get(g.classification, 99),
                -g.severity,
            )
        )

        # Compute deltas
        prior_gaps = prior_briefing.top_gaps if prior_briefing else []
        deltas = GapDetector.compute_delta(all_gaps, prior_gaps)

        # Rank recommendations
        recommendations = self._rank_recommendations(all_gaps)

        # Total cost
        total_cost = sum(fr.cost_usd for fr in framework_results)

        week_of = datetime.utcnow().strftime("%Y-W%V")

        briefing = WeeklyBriefing(
            tenant=tenant,
            week_of=week_of,
            framework_results=framework_results,
            top_gaps=all_gaps[:15],
            deltas_from_prior=deltas,
            recommendations=recommendations,
            total_cost_usd=round(total_cost, 4),
        )

        self._persist(briefing)
        return briefing

    def _rank_recommendations(self, gaps: list[Gap]) -> list[dict[str, Any]]:
        """Rank recommendations by gap severity and classification."""
        recs = []
        for i, gap in enumerate(gaps):
            if not gap.recommendation:
                continue
            recs.append({
                "rank": i + 1,
                "framework": gap.framework,
                "classification": gap.classification.value,
                "severity": gap.severity,
                "description": gap.description,
                "recommendation": gap.recommendation,
                "gap_id": gap.id,
            })
        return recs[:10]

    def _load_prior(self, tenant: str) -> WeeklyBriefing | None:
        """Load the most recent prior briefing from disk."""
        briefing_dir = self._data_dir / tenant / "briefings"
        if not briefing_dir.exists():
            return None

        files = sorted(briefing_dir.glob("*.json"), reverse=True)
        if not files:
            return None

        try:
            data = json.loads(files[0].read_text())
            return WeeklyBriefing(**data)
        except Exception as exc:
            logger.debug("briefing.load_prior_failed", error=str(exc))
            return None

    def _persist(self, briefing: WeeklyBriefing) -> Path:
        """Write briefing to disk."""
        briefing_dir = self._data_dir / briefing.tenant / "briefings"
        briefing_dir.mkdir(parents=True, exist_ok=True)

        filename = f"{briefing.week_of}_{briefing.id}.json"
        path = briefing_dir / filename
        path.write_text(
            json.dumps(briefing.model_dump(), indent=2, default=str)
        )
        logger.info("briefing.persisted", path=str(path))
        return path

    @staticmethod
    def render_markdown(briefing: WeeklyBriefing) -> str:
        """Render the briefing as human-readable markdown."""
        lines = [
            f"# Strategic Intelligence Briefing — {briefing.tenant.upper()}",
            f"**Week:** {briefing.week_of} | "
            f"**Generated:** {briefing.generated_at.strftime('%Y-%m-%d %H:%M UTC')} | "
            f"**Cost:** ${briefing.total_cost_usd:.2f}",
            "",
        ]

        # Deltas section (what changed)
        new_gaps = [d for d in briefing.deltas_from_prior if d["type"] == "new_gap"]
        resolved = [d for d in briefing.deltas_from_prior if d["type"] == "resolved"]
        escalated = [d for d in briefing.deltas_from_prior if d["type"] == "escalated"]

        if briefing.deltas_from_prior:
            lines.append("## What Changed This Week")
            if new_gaps:
                lines.append(f"**{len(new_gaps)} new gaps detected:**")
                for d in new_gaps[:5]:
                    lines.append(f"- {d['description'][:100]} (severity: {d['current_severity']:.1f})")
            if escalated:
                lines.append(f"\n**{len(escalated)} gaps escalated:**")
                for d in escalated[:3]:
                    lines.append(
                        f"- {d['description'][:100]} "
                        f"({d['prior_severity']:.1f} -> {d['current_severity']:.1f})"
                    )
            if resolved:
                lines.append(f"\n**{len(resolved)} gaps resolved:**")
                for d in resolved[:3]:
                    lines.append(f"- ~~{d['description'][:100]}~~")
            lines.append("")

        # Top gaps
        lines.append("## Top Gaps")
        for gap in briefing.top_gaps[:10]:
            icon = {
                "blind_spot": "[BLIND SPOT]",
                "threat": "[THREAT]",
                "opportunity": "[OPPORTUNITY]",
                "confirmed": "[CONFIRMED]",
            }.get(gap.classification.value, "[?]")
            lines.append(
                f"- **{icon}** (severity {gap.severity:.1f}) "
                f"{gap.description[:150]}"
            )
        lines.append("")

        # Recommendations
        if briefing.recommendations:
            lines.append("## Recommended Actions")
            for rec in briefing.recommendations[:5]:
                lines.append(
                    f"{rec['rank']}. **[{rec['framework']}]** "
                    f"{rec['recommendation']}"
                )
            lines.append("")

        # Framework summaries
        lines.append("## Framework Results")
        for fr in briefing.framework_results:
            lines.append(
                f"- **{fr.framework_name}**: "
                f"{len(fr.gaps)} gaps, "
                f"{len(fr.external_signals)} signals, "
                f"${fr.cost_usd:.3f}"
            )

        return "\n".join(lines)
