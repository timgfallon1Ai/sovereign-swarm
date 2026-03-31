"""Website change monitor for competitor tracking."""

from __future__ import annotations

import difflib
import hashlib
from datetime import datetime
from typing import Any

import structlog

from sovereign_swarm.competitive_intel.models import (
    ChangeType,
    CompetitorChange,
)

logger = structlog.get_logger()


class WebsiteSnapshot:
    """A point-in-time snapshot of a webpage."""

    def __init__(self, url: str, content: str, fetched_at: datetime) -> None:
        self.url = url
        self.content = content
        self.fetched_at = fetched_at
        self.content_hash = hashlib.sha256(content.encode()).hexdigest()


class WebsiteMonitor:
    """Tracks competitor website changes.

    Monitors pricing pages, feature pages, and blog posts using httpx
    and difflib to detect changes. Stores snapshots for comparison.
    """

    def __init__(self) -> None:
        self._snapshots: dict[str, list[WebsiteSnapshot]] = {}  # url -> history
        self._http_client = None

    async def fetch_page(self, url: str) -> WebsiteSnapshot:
        """Fetch a webpage and create a snapshot."""
        client = self._get_client()
        try:
            response = await client.get(url, follow_redirects=True, timeout=15.0)
            response.raise_for_status()
            content = response.text
        except Exception as e:
            logger.error("website_monitor.fetch_failed", url=url, error=str(e))
            content = f"[Fetch failed: {e}]"

        snapshot = WebsiteSnapshot(
            url=url,
            content=content,
            fetched_at=datetime.now(),
        )

        # Store in history
        self._snapshots.setdefault(url, []).append(snapshot)
        return snapshot

    async def check_for_changes(
        self, url: str, competitor_id: str = "", competitor_name: str = ""
    ) -> CompetitorChange | None:
        """Fetch a page and compare to the last snapshot."""
        history = self._snapshots.get(url, [])

        new_snapshot = await self.fetch_page(url)

        if len(history) < 2:
            # First or second fetch -- no comparison possible
            return None

        previous = history[-2]
        if previous.content_hash == new_snapshot.content_hash:
            return None

        # Detect what changed
        diff = self._compute_diff(previous.content, new_snapshot.content)
        change_type = self._classify_change(diff, url)

        return CompetitorChange(
            competitor_id=competitor_id,
            competitor_name=competitor_name,
            change_type=change_type,
            old_value=f"Snapshot from {previous.fetched_at.isoformat()}",
            new_value=f"Changed detected at {new_snapshot.fetched_at.isoformat()}",
            detected_at=new_snapshot.fetched_at,
            significance=self._assess_significance(diff),
            notes=self._summarize_diff(diff),
        )

    def get_snapshot_history(self, url: str) -> list[dict[str, Any]]:
        """Return snapshot history for a URL."""
        history = self._snapshots.get(url, [])
        return [
            {
                "url": s.url,
                "fetched_at": s.fetched_at.isoformat(),
                "content_hash": s.content_hash,
                "content_length": len(s.content),
            }
            for s in history
        ]

    @staticmethod
    def _compute_diff(old: str, new: str) -> list[str]:
        """Compute unified diff between two content versions."""
        old_lines = old.splitlines(keepends=True)
        new_lines = new.splitlines(keepends=True)
        return list(difflib.unified_diff(old_lines, new_lines, n=3))

    @staticmethod
    def _classify_change(diff: list[str], url: str) -> ChangeType:
        """Classify the type of change detected."""
        diff_text = "".join(diff).lower()
        url_lower = url.lower()

        if any(kw in url_lower for kw in ("pricing", "plans", "cost")):
            return ChangeType.PRICING
        if any(kw in diff_text for kw in ("price", "$", "per month", "per year")):
            return ChangeType.PRICING
        if any(kw in url_lower for kw in ("features", "product", "solutions")):
            return ChangeType.FEATURE
        if any(kw in url_lower for kw in ("blog", "news", "updates")):
            return ChangeType.CONTENT
        return ChangeType.OTHER

    @staticmethod
    def _assess_significance(diff: list[str]) -> str:
        """Assess the significance of changes."""
        added = sum(1 for line in diff if line.startswith("+") and not line.startswith("+++"))
        removed = sum(1 for line in diff if line.startswith("-") and not line.startswith("---"))
        total_changes = added + removed

        if total_changes > 50:
            return "high"
        elif total_changes > 15:
            return "medium"
        return "low"

    @staticmethod
    def _summarize_diff(diff: list[str]) -> str:
        """Create a brief summary of changes."""
        added = sum(1 for l in diff if l.startswith("+") and not l.startswith("+++"))
        removed = sum(1 for l in diff if l.startswith("-") and not l.startswith("---"))
        return f"{added} lines added, {removed} lines removed"

    def _get_client(self):
        if self._http_client is None:
            try:
                import httpx

                self._http_client = httpx.AsyncClient(
                    headers={"User-Agent": "SovereignSwarm/0.1 CompetitiveIntel"}
                )
            except ImportError:
                raise RuntimeError("httpx is required for WebsiteMonitor")
        return self._http_client
