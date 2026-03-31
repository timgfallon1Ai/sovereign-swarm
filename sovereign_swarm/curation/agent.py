"""CurationAgent -- knowledge curation for the Sovereign AI swarm."""

from __future__ import annotations

from typing import Any

import structlog

from sovereign_swarm.protocol.swarm_agent import (
    SwarmAgent,
    SwarmAgentCard,
    SwarmAgentRequest,
    SwarmAgentResponse,
)

logger = structlog.get_logger()


class CurationAgent(SwarmAgent):
    """Curates the knowledge base: dedup, freshness, taxonomy, reading lists, quality."""

    def __init__(self, config: Any | None = None) -> None:
        self.config = config
        self._dedup: Any | None = None
        self._freshness: Any | None = None
        self._taxonomy: Any | None = None
        self._reading_list: Any | None = None

    @property
    def card(self) -> SwarmAgentCard:
        return SwarmAgentCard(
            name="curation",
            description=(
                "Knowledge curation agent -- finds duplicates, checks freshness, "
                "maintains taxonomy, generates reading lists, produces quality reports"
            ),
            domains=["curation", "quality", "taxonomy", "reading", "knowledge_management"],
            supported_intents=[
                "find_duplicates",
                "check_freshness",
                "update_taxonomy",
                "generate_reading_list",
                "quality_report",
            ],
            capabilities=[
                "find_duplicates",
                "check_freshness",
                "update_taxonomy",
                "generate_reading_list",
                "quality_report",
            ],
        )

    async def execute(self, request: SwarmAgentRequest) -> SwarmAgentResponse:
        """Route curation requests to the appropriate handler."""
        task = request.task.lower()

        try:
            if "duplic" in task or "dedup" in task:
                result = await self._handle_duplicates(request)
            elif "fresh" in task or "outdated" in task or "stale" in task:
                result = await self._handle_freshness(request)
            elif "taxonom" in task or "categor" in task:
                result = await self._handle_taxonomy(request)
            elif "reading" in task or "list" in task:
                result = await self._handle_reading_list(request)
            elif "quality" in task or "report" in task:
                result = await self._handle_quality_report(request)
            else:
                result = await self._handle_quality_report(request)

            return SwarmAgentResponse(
                agent_name="curation",
                status="success",
                output=result.get("markdown", str(result)),
                data=result,
                confidence=0.8,
            )
        except Exception as e:
            logger.error("curation.execute_failed", error=str(e))
            return SwarmAgentResponse(
                agent_name="curation",
                status="error",
                error=str(e),
            )

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------

    async def _handle_duplicates(self, request: SwarmAgentRequest) -> dict:
        documents = request.parameters.get("documents", [])
        if not documents:
            return {"markdown": "No documents provided for duplicate detection."}

        detector = self._get_dedup()
        clusters = detector.find_duplicates(documents)

        lines = [f"## Duplicate Scan: {len(clusters)} clusters found\n"]
        for i, cluster in enumerate(clusters, 1):
            lines.append(
                f"- **Cluster {i}**: {len(cluster.document_ids)} docs, "
                f"similarity {cluster.similarity_score:.1%}, "
                f"action: {cluster.recommended_action}"
            )
            for doc_id in cluster.document_ids:
                lines.append(f"  - {doc_id}")

        return {
            "markdown": "\n".join(lines),
            "clusters": [c.model_dump() for c in clusters],
        }

    async def _handle_freshness(self, request: SwarmAgentRequest) -> dict:
        documents = request.parameters.get("documents", [])
        if not documents:
            return {"markdown": "No documents provided for freshness check."}

        checker = self._get_freshness()
        outdated = checker.check_freshness(documents)
        superseded = checker.find_superseded(documents)

        lines = [
            f"## Freshness Report",
            f"**Outdated**: {len(outdated)} documents",
            f"**Superseded**: {len(superseded)} documents\n",
        ]
        for od in outdated[:20]:
            lines.append(f"- {od.document_id}: {od.reason}")
        for sp in superseded[:10]:
            lines.append(f"- {sp.document_id}: superseded by {sp.superseded_by}")

        return {
            "markdown": "\n".join(lines),
            "outdated": [o.model_dump() for o in outdated],
            "superseded": [s.model_dump() for s in superseded],
        }

    async def _handle_taxonomy(self, request: SwarmAgentRequest) -> dict:
        documents = request.parameters.get("documents", [])
        manager = self._get_taxonomy()

        if documents:
            taxonomy = manager.build_from_documents(documents)
        else:
            taxonomy = manager.get_taxonomy()

        suggestions = manager.suggest_new_categories(documents) if documents else []

        lines = [f"## Topic Taxonomy: {len(taxonomy)} categories\n"]
        for topic in taxonomy:
            subtopic_str = ", ".join(topic.subtopics[:5])
            lines.append(f"- **{topic.name}** ({topic.document_count} docs): {subtopic_str}")

        if suggestions:
            lines.append(f"\n**Suggested new categories**: {', '.join(suggestions[:10])}")

        return {
            "markdown": "\n".join(lines),
            "taxonomy": [t.model_dump() for t in taxonomy],
            "suggestions": suggestions,
        }

    async def _handle_reading_list(self, request: SwarmAgentRequest) -> dict:
        documents = request.parameters.get("documents", [])
        topic = request.parameters.get("topic", "")
        max_items = request.parameters.get("max_items", 10)

        if not documents:
            return {"markdown": "No documents provided to generate reading list."}

        generator = self._get_reading_list()
        reading_list = generator.generate(documents, topic=topic, max_items=max_items)

        lines = [
            f"## {reading_list.title}",
            f"*{reading_list.description}*",
            f"Estimated reading time: {reading_list.estimated_time_hours} hours\n",
        ]
        for i, doc in enumerate(reading_list.documents, 1):
            lines.append(
                f"{i}. **{doc['title']}** ({doc['estimated_minutes']:.0f} min)"
            )

        return {
            "markdown": "\n".join(lines),
            "reading_list": reading_list.model_dump(),
        }

    async def _handle_quality_report(self, request: SwarmAgentRequest) -> dict:
        documents = request.parameters.get("documents", [])
        source = request.parameters.get("source", "all")

        from sovereign_swarm.curation.models import QualityReport

        if not documents:
            report = QualityReport(source=source, document_count=0, issues=["No documents provided"])
            return {"markdown": "## Quality Report\n\nNo documents provided.", "report": report.model_dump()}

        # Compute quality metrics
        scores = [doc.get("quality_score", 0.5) for doc in documents]
        avg_score = sum(scores) / len(scores) if scores else 0.0
        low_quality = [doc for doc in documents if doc.get("quality_score", 0.5) < 0.3]

        issues: list[str] = []
        for doc in low_quality:
            issues.append(f"Low quality: {doc.get('title', doc.get('id', '?'))}")

        report = QualityReport(
            source=source,
            document_count=len(documents),
            avg_quality_score=round(avg_score, 3),
            low_quality_count=len(low_quality),
            issues=issues,
        )

        lines = [
            f"## Quality Report: {source}",
            f"**Documents**: {report.document_count}",
            f"**Avg quality**: {report.avg_quality_score:.1%}",
            f"**Low quality**: {report.low_quality_count}",
        ]
        if issues:
            lines.append("\n**Issues:**")
            for issue in issues[:10]:
                lines.append(f"- {issue}")

        return {"markdown": "\n".join(lines), "report": report.model_dump()}

    # ------------------------------------------------------------------
    # Lazy accessors
    # ------------------------------------------------------------------

    def _get_dedup(self):
        if self._dedup is None:
            from sovereign_swarm.curation.dedup import DuplicateDetector

            self._dedup = DuplicateDetector()
        return self._dedup

    def _get_freshness(self):
        if self._freshness is None:
            from sovereign_swarm.curation.freshness import FreshnessChecker

            self._freshness = FreshnessChecker()
        return self._freshness

    def _get_taxonomy(self):
        if self._taxonomy is None:
            from sovereign_swarm.curation.taxonomy import TaxonomyManager

            self._taxonomy = TaxonomyManager()
        return self._taxonomy

    def _get_reading_list(self):
        if self._reading_list is None:
            from sovereign_swarm.curation.reading_list import ReadingListGenerator

            self._reading_list = ReadingListGenerator()
        return self._reading_list
