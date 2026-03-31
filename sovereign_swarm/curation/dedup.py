"""Duplicate detection across document sources."""

from __future__ import annotations

import difflib
import hashlib
from typing import Any

import structlog

from sovereign_swarm.curation.models import DuplicateCluster

logger = structlog.get_logger()


class DuplicateDetector:
    """Finds near-duplicate documents using title/abstract similarity.

    Phase A: uses difflib SequenceMatcher for similarity.
    Phase B: integrates sovereign-ingest's MinHash LSH deduplicator.
    """

    def __init__(self, similarity_threshold: float = 0.85) -> None:
        self._threshold = similarity_threshold

    def find_duplicates(
        self, documents: list[dict[str, Any]]
    ) -> list[DuplicateCluster]:
        """Find clusters of near-duplicate documents.

        Each document dict should have at minimum: id, title, and optionally text/abstract.
        """
        if not documents:
            return []

        clusters: list[DuplicateCluster] = []
        seen: set[str] = set()

        for i, doc_a in enumerate(documents):
            if doc_a["id"] in seen:
                continue

            cluster_ids = [doc_a["id"]]
            max_sim = 0.0

            for j, doc_b in enumerate(documents[i + 1 :], start=i + 1):
                if doc_b["id"] in seen:
                    continue

                sim = self._compute_similarity(doc_a, doc_b)
                if sim >= self._threshold:
                    cluster_ids.append(doc_b["id"])
                    max_sim = max(max_sim, sim)
                    seen.add(doc_b["id"])

            if len(cluster_ids) > 1:
                seen.add(doc_a["id"])
                clusters.append(
                    DuplicateCluster(
                        document_ids=cluster_ids,
                        similarity_score=round(max_sim, 4),
                        recommended_action=self._recommend_action(max_sim),
                    )
                )

        logger.info(
            "dedup.scan_complete",
            documents=len(documents),
            clusters=len(clusters),
        )
        return clusters

    def _compute_similarity(
        self, doc_a: dict[str, Any], doc_b: dict[str, Any]
    ) -> float:
        """Compute similarity between two documents using title + text."""
        # Title similarity (weighted higher)
        title_sim = difflib.SequenceMatcher(
            None,
            doc_a.get("title", "").lower(),
            doc_b.get("title", "").lower(),
        ).ratio()

        # Content similarity (abstract or first 1000 chars of text)
        text_a = (doc_a.get("abstract", "") or doc_a.get("text", ""))[:1000]
        text_b = (doc_b.get("abstract", "") or doc_b.get("text", ""))[:1000]

        if text_a and text_b:
            text_sim = difflib.SequenceMatcher(None, text_a.lower(), text_b.lower()).ratio()
            return 0.4 * title_sim + 0.6 * text_sim
        else:
            return title_sim

    @staticmethod
    def _recommend_action(similarity: float) -> str:
        if similarity >= 0.98:
            return "remove"
        elif similarity >= 0.92:
            return "keep_best"
        elif similarity >= 0.85:
            return "merge"
        else:
            return "review"

    @staticmethod
    def content_hash(text: str) -> str:
        """Generate a content hash for exact-duplicate detection."""
        normalized = " ".join(text.lower().split())
        return hashlib.sha256(normalized.encode()).hexdigest()
