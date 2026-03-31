"""Topic taxonomy management for the knowledge base."""

from __future__ import annotations

from collections import Counter
from typing import Any

import structlog

from sovereign_swarm.curation.models import TopicTaxonomy

logger = structlog.get_logger()


class TaxonomyManager:
    """Maintains and auto-generates the topic hierarchy for the knowledge base."""

    def __init__(self) -> None:
        self._taxonomy: dict[str, TopicTaxonomy] = {}

    def build_from_documents(
        self, documents: list[dict[str, Any]]
    ) -> list[TopicTaxonomy]:
        """Auto-generate taxonomy from document categories and tags.

        Each document dict should have: id, category (str), tags (list[str]).
        """
        category_counter: Counter[str] = Counter()
        category_subtopics: dict[str, Counter[str]] = {}

        for doc in documents:
            category = doc.get("category", "uncategorized")
            tags = doc.get("tags", [])

            category_counter[category] += 1
            if category not in category_subtopics:
                category_subtopics[category] = Counter()
            for tag in tags:
                category_subtopics[category][tag] += 1

        taxonomy_list: list[TopicTaxonomy] = []
        for category, count in category_counter.most_common():
            subtopics = [
                tag for tag, _ in category_subtopics.get(category, Counter()).most_common(20)
            ]
            topic = TopicTaxonomy(
                name=category,
                subtopics=subtopics,
                document_count=count,
            )
            self._taxonomy[category] = topic
            taxonomy_list.append(topic)

        logger.info(
            "taxonomy.built",
            categories=len(taxonomy_list),
            documents=len(documents),
        )
        return taxonomy_list

    def suggest_new_categories(
        self, documents: list[dict[str, Any]], min_cluster_size: int = 3
    ) -> list[str]:
        """Suggest new categories based on frequently co-occurring tags not in the taxonomy.

        Returns tag names that appear in >= min_cluster_size documents but aren't top-level categories.
        """
        tag_counter: Counter[str] = Counter()
        for doc in documents:
            for tag in doc.get("tags", []):
                tag_counter[tag] += 1

        existing = set(self._taxonomy.keys())
        suggestions = [
            tag
            for tag, count in tag_counter.most_common()
            if count >= min_cluster_size and tag not in existing
        ]
        return suggestions[:20]

    def get_taxonomy(self) -> list[TopicTaxonomy]:
        """Return the current taxonomy."""
        return list(self._taxonomy.values())

    def add_topic(self, name: str, subtopics: list[str] | None = None) -> TopicTaxonomy:
        """Manually add a topic to the taxonomy."""
        topic = TopicTaxonomy(name=name, subtopics=subtopics or [])
        self._taxonomy[name] = topic
        return topic

    def remove_topic(self, name: str) -> bool:
        """Remove a topic from the taxonomy."""
        return self._taxonomy.pop(name, None) is not None
