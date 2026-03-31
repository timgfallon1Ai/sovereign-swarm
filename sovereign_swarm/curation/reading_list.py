"""Reading list generation for curated knowledge consumption."""

from __future__ import annotations

from typing import Any

import structlog

from sovereign_swarm.curation.models import ReadingList

logger = structlog.get_logger()

# Average reading speed: ~250 words/min, ~1500 words per page
_WORDS_PER_MINUTE = 250


class ReadingListGenerator:
    """Generates curated reading lists based on interests, projects, or goals."""

    def generate(
        self,
        documents: list[dict[str, Any]],
        topic: str = "",
        max_items: int = 10,
        difficulty: str = "intermediate",
    ) -> ReadingList:
        """Generate a curated reading list from a set of documents.

        Each document dict should have: id, title, abstract/text,
        optionally: quality_score, word_count, tags, difficulty.
        """
        # Filter by topic if specified
        if topic:
            filtered = self._filter_by_topic(documents, topic)
        else:
            filtered = documents

        # Sort by relevance/quality
        ranked = self._rank_documents(filtered, topic)

        # Take top N
        selected = ranked[:max_items]

        # Build reading list entries
        entries: list[dict[str, Any]] = []
        total_minutes = 0.0

        for doc in selected:
            word_count = doc.get("word_count", 0)
            if not word_count:
                # Estimate from text/abstract
                text = doc.get("text", "") or doc.get("abstract", "")
                word_count = len(text.split())

            read_time_min = word_count / _WORDS_PER_MINUTE
            total_minutes += read_time_min

            entries.append(
                {
                    "id": doc.get("id", ""),
                    "title": doc.get("title", "Untitled"),
                    "abstract": (doc.get("abstract", "") or doc.get("text", ""))[:300],
                    "estimated_minutes": round(read_time_min, 1),
                    "quality_score": doc.get("quality_score", 0.0),
                    "tags": doc.get("tags", []),
                }
            )

        return ReadingList(
            title=f"Reading List: {topic}" if topic else "Curated Reading List",
            documents=entries,
            estimated_time_hours=round(total_minutes / 60, 1),
            difficulty=difficulty,
            description=f"{len(entries)} documents selected"
            + (f" on '{topic}'" if topic else ""),
        )

    @staticmethod
    def _filter_by_topic(
        documents: list[dict[str, Any]], topic: str
    ) -> list[dict[str, Any]]:
        """Filter documents by topic keyword match in title, tags, and abstract."""
        topic_lower = topic.lower()
        result: list[dict[str, Any]] = []
        for doc in documents:
            title = doc.get("title", "").lower()
            tags = [t.lower() for t in doc.get("tags", [])]
            abstract = (doc.get("abstract", "") or doc.get("text", "")).lower()[:500]

            if topic_lower in title or topic_lower in tags or topic_lower in abstract:
                result.append(doc)
        return result

    @staticmethod
    def _rank_documents(
        documents: list[dict[str, Any]], topic: str = ""
    ) -> list[dict[str, Any]]:
        """Rank documents by quality score and relevance."""

        def score(doc: dict[str, Any]) -> float:
            quality = doc.get("quality_score", 0.5)
            # Boost if topic appears in title
            if topic and topic.lower() in doc.get("title", "").lower():
                quality += 0.2
            return quality

        return sorted(documents, key=score, reverse=True)
