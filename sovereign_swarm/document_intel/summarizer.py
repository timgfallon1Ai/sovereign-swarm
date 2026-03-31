"""Document summarization -- heuristic extraction with optional Claude enhancement."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

import structlog

from sovereign_swarm.document_intel.models import DocumentSummary

logger = structlog.get_logger()

# Patterns for heuristic extraction
_DATE_PATTERN = re.compile(
    r"\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}[/-]\d{1,2}[/-]\d{1,2}"
    r"|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\s+\d{1,2},?\s*\d{4})\b",
    re.IGNORECASE,
)
_AMOUNT_PATTERN = re.compile(
    r"\$[\d,]+(?:\.\d{2})?|\b\d{1,3}(?:,\d{3})+(?:\.\d{2})?\b"
)
_ACTION_KEYWORDS = re.compile(
    r"(?:must|shall|should|will|need to|required to|action item|todo|follow[- ]up|deadline|due)",
    re.IGNORECASE,
)


class DocumentSummarizer:
    """Summarize documents using heuristic extraction or Claude."""

    def __init__(self, anthropic_client: Any | None = None) -> None:
        self._client = anthropic_client

    def summarize(self, text: str, title: str = "") -> DocumentSummary:
        """Generate a structured summary of the document text."""
        if not text.strip():
            return DocumentSummary(title=title)

        key_points = self._extract_key_points(text)
        entities = self._extract_entities(text)
        dates = self._extract_dates(text)
        amounts = self._extract_amounts(text)
        action_items = self._extract_action_items(text)

        if not title:
            title = self._guess_title(text)

        return DocumentSummary(
            title=title,
            key_points=key_points,
            entities=entities,
            dates=dates,
            amounts=amounts,
            action_items=action_items,
        )

    # ------------------------------------------------------------------
    # Heuristic extractors
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_key_points(text: str, max_points: int = 10) -> list[str]:
        """Extract key points: first sentence of each paragraph, plus sentences with numbers."""
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        points: list[str] = []

        for para in paragraphs[:max_points]:
            sentences = re.split(r"(?<=[.!?])\s+", para)
            if sentences:
                first = sentences[0].strip()
                if len(first) > 20:  # skip very short fragments
                    points.append(first)

        return points[:max_points]

    @staticmethod
    def _extract_entities(text: str) -> list[str]:
        """Extract likely named entities (capitalized multi-word phrases)."""
        # Simple heuristic: find capitalized sequences that aren't sentence starts
        entity_pattern = re.compile(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b")
        matches = entity_pattern.findall(text)
        # Deduplicate while preserving order
        seen: set[str] = set()
        entities: list[str] = []
        for m in matches:
            if m not in seen and len(m) > 3:
                seen.add(m)
                entities.append(m)
        return entities[:30]

    @staticmethod
    def _extract_dates(text: str) -> list[str]:
        """Extract date strings from text."""
        matches = _DATE_PATTERN.findall(text)
        return list(dict.fromkeys(matches))[:20]

    @staticmethod
    def _extract_amounts(text: str) -> list[str]:
        """Extract monetary amounts from text."""
        matches = _AMOUNT_PATTERN.findall(text)
        return list(dict.fromkeys(matches))[:20]

    @staticmethod
    def _extract_action_items(text: str) -> list[str]:
        """Extract sentences that look like action items."""
        sentences = re.split(r"(?<=[.!?])\s+", text)
        items: list[str] = []
        for sentence in sentences:
            if _ACTION_KEYWORDS.search(sentence):
                clean = sentence.strip()
                if 10 < len(clean) < 500:
                    items.append(clean)
        return items[:20]

    @staticmethod
    def _guess_title(text: str) -> str:
        """Guess the document title from the first non-empty line."""
        for line in text.splitlines():
            stripped = line.strip()
            if stripped and len(stripped) < 200:
                return stripped
        return "Untitled Document"
