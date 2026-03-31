"""Freshness checking for knowledge base documents."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import structlog

from sovereign_swarm.curation.models import OutdatedDocument

logger = structlog.get_logger()

# Default staleness thresholds (days)
_THRESHOLDS: dict[str, int] = {
    "market_data": 1,
    "news": 7,
    "research_paper": 365,
    "regulatory": 90,
    "default": 180,
}


class FreshnessChecker:
    """Identifies outdated content in the knowledge base."""

    def __init__(self, thresholds: dict[str, int] | None = None) -> None:
        self._thresholds = thresholds or _THRESHOLDS

    def check_freshness(
        self, documents: list[dict[str, Any]], now: datetime | None = None
    ) -> list[OutdatedDocument]:
        """Identify outdated documents based on type-specific thresholds.

        Each document dict should have: id, title, doc_type, published_date or ingested_at.
        Optionally: authors, source.
        """
        now = now or datetime.utcnow()
        outdated: list[OutdatedDocument] = []

        for doc in documents:
            doc_type = doc.get("doc_type", "default")
            threshold_days = self._thresholds.get(doc_type, self._thresholds["default"])
            cutoff = now - timedelta(days=threshold_days)

            # Check publication / ingestion date
            pub_date = doc.get("published_date") or doc.get("ingested_at")
            if isinstance(pub_date, str):
                try:
                    pub_date = datetime.fromisoformat(pub_date)
                except ValueError:
                    pub_date = None

            if pub_date and pub_date < cutoff:
                age_days = (now - pub_date).days
                outdated.append(
                    OutdatedDocument(
                        document_id=doc["id"],
                        reason=f"Document is {age_days} days old (threshold: {threshold_days} days for {doc_type})",
                        confidence=min(1.0, age_days / (threshold_days * 2)),
                    )
                )

        logger.info(
            "freshness.check_complete",
            total=len(documents),
            outdated=len(outdated),
        )
        return outdated

    def find_superseded(
        self, documents: list[dict[str, Any]]
    ) -> list[OutdatedDocument]:
        """Find papers superseded by newer versions (same authors, similar title).

        Uses heuristic: same first author + title similarity > 0.8 + newer date.
        """
        import difflib

        superseded: list[OutdatedDocument] = []

        # Group by first author
        by_author: dict[str, list[dict[str, Any]]] = {}
        for doc in documents:
            authors = doc.get("authors", [])
            first_author = authors[0].lower().strip() if authors else ""
            if first_author:
                by_author.setdefault(first_author, []).append(doc)

        for author, docs in by_author.items():
            if len(docs) < 2:
                continue

            # Sort by date descending
            docs_sorted = sorted(
                docs,
                key=lambda d: d.get("published_date", "") or "",
                reverse=True,
            )

            for i, newer in enumerate(docs_sorted):
                for older in docs_sorted[i + 1 :]:
                    title_sim = difflib.SequenceMatcher(
                        None,
                        newer.get("title", "").lower(),
                        older.get("title", "").lower(),
                    ).ratio()

                    if title_sim > 0.8:
                        superseded.append(
                            OutdatedDocument(
                                document_id=older["id"],
                                reason=f"Likely superseded by newer version from same author ({author})",
                                superseded_by=newer["id"],
                                confidence=round(title_sim, 3),
                            )
                        )

        return superseded
