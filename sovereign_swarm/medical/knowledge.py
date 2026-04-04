"""MedicalKnowledgeEngine -- interfaces with sovereign-ingest for medical data."""

from __future__ import annotations

from typing import Any

import structlog

from sovereign_swarm.integration.ingest_bridge import SovereignIngestBridge

logger = structlog.get_logger()


class MedicalKnowledgeEngine:
    """Search ingested medical knowledge via sovereign-ingest bridge."""

    def __init__(self, ingest_bridge: SovereignIngestBridge) -> None:
        self._ingest = ingest_bridge

    @property
    def available(self) -> bool:
        return self._ingest.available

    async def search_pubmed(
        self, query: str, limit: int = 10
    ) -> list[dict[str, Any]]:
        """Search ingested PubMed abstracts."""
        if not self.available:
            return []
        result = await self._ingest.search(
            query=query, source="pubmed", limit=limit
        )
        return result.get("results", [])

    async def search_clinical_trials(
        self, condition: str, limit: int = 10
    ) -> list[dict[str, Any]]:
        """Search ingested clinical trial records."""
        if not self.available:
            return []
        result = await self._ingest.search(
            query=condition, source="clinicaltrials", limit=limit
        )
        return result.get("results", [])

    async def search_drug_info(
        self, drug_name: str
    ) -> list[dict[str, Any]]:
        """Search ingested drug data (DrugBank, etc.)."""
        if not self.available:
            return []
        result = await self._ingest.search(
            query=drug_name, source="drugbank", limit=10
        )
        return result.get("results", [])

    async def search_medical_literature(
        self,
        query: str,
        sources: list[str] | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Cross-source medical search across multiple knowledge sources."""
        if not self.available:
            return []

        all_results: list[dict[str, Any]] = []
        target_sources = sources or ["pubmed", "clinicaltrials", "drugbank"]

        for source in target_sources:
            try:
                result = await self._ingest.search(
                    query=query, source=source, limit=limit
                )
                for item in result.get("results", []):
                    item["_source"] = source
                    all_results.append(item)
            except Exception as exc:
                logger.warning(
                    "medical_knowledge.source_search_failed",
                    source=source,
                    error=str(exc),
                )

        # Sort by relevance score if present, descending
        all_results.sort(
            key=lambda r: r.get("score", r.get("relevance_score", 0)),
            reverse=True,
        )
        return all_results[:limit]

    async def get_drug_interactions(
        self, drug_list: list[str]
    ) -> list[dict[str, Any]]:
        """Check known interactions from DrugBank data for a list of drugs."""
        if not self.available:
            return []

        interactions: list[dict[str, Any]] = []
        for i, drug_a in enumerate(drug_list):
            for drug_b in drug_list[i + 1 :]:
                query = f"{drug_a} {drug_b} interaction"
                result = await self._ingest.search(
                    query=query, source="drugbank", limit=5
                )
                for item in result.get("results", []):
                    interactions.append(
                        {
                            "drug_a": drug_a,
                            "drug_b": drug_b,
                            "raw": item,
                        }
                    )
        return interactions
