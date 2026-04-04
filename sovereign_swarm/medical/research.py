"""ClinicalResearcher -- medical literature search and research reports."""

from __future__ import annotations

from typing import Any

import structlog

from sovereign_swarm.medical.knowledge import MedicalKnowledgeEngine
from sovereign_swarm.medical.models import (
    MEDICAL_DISCLAIMER,
    ClinicalResearchResult,
    MedicalDomain,
)

logger = structlog.get_logger()

# Map medical domains to preferred knowledge sources
_DOMAIN_SOURCE_MAP: dict[MedicalDomain, list[str]] = {
    MedicalDomain.PHARMACOLOGY: ["drugbank", "pubmed", "clinicaltrials"],
    MedicalDomain.ONCOLOGY: ["clinicaltrials", "pubmed"],
    MedicalDomain.RADIOLOGY: ["pubmed"],
    MedicalDomain.DENTISTRY: ["pubmed"],
    MedicalDomain.ORTHOPEDICS: ["pubmed", "clinicaltrials"],
    MedicalDomain.REGENERATIVE_MEDICINE: ["pubmed", "clinicaltrials"],
    MedicalDomain.NEUROSCIENCE: ["pubmed", "clinicaltrials"],
    MedicalDomain.CELLULAR_BIOLOGY: ["pubmed"],
    MedicalDomain.GENERAL: ["pubmed", "clinicaltrials", "drugbank"],
}


class ClinicalResearcher:
    """Search medical literature and compose research reports."""

    def __init__(self, knowledge: MedicalKnowledgeEngine) -> None:
        self._knowledge = knowledge

    async def search_literature(
        self,
        query: str,
        domain: MedicalDomain = MedicalDomain.GENERAL,
        limit: int = 20,
    ) -> list[ClinicalResearchResult]:
        """Search literature, routing to appropriate sources by domain."""
        sources = _DOMAIN_SOURCE_MAP.get(domain, ["pubmed"])
        raw_results = await self._knowledge.search_medical_literature(
            query=query, sources=sources, limit=limit
        )
        return self._convert_results(raw_results)

    async def search_trials(
        self,
        condition: str,
        limit: int = 20,
    ) -> list[ClinicalResearchResult]:
        """Search clinical trials specifically."""
        raw_results = await self._knowledge.search_clinical_trials(
            condition=condition, limit=limit
        )
        return self._convert_results(raw_results, default_source="clinicaltrials")

    async def compose_report(
        self,
        query: str,
        domain: MedicalDomain = MedicalDomain.GENERAL,
        limit: int = 20,
    ) -> str:
        """Compose a multi-source research report (ScientistAgent pattern)."""
        results = await self.search_literature(query, domain, limit)

        if not results:
            return (
                f"No results found for: {query}\n\n"
                f"**Disclaimer:** {MEDICAL_DISCLAIMER}"
            )

        lines = [f"## Clinical Research Report: {query}\n"]
        lines.append(f"**Domain:** {domain.value}")
        lines.append(f"**Results found:** {len(results)}\n")

        for i, r in enumerate(results, 1):
            lines.append(f"### {i}. {r.title}")
            lines.append(f"**Source:** {r.source}")
            if r.pmid_or_nctid:
                lines.append(f"**ID:** {r.pmid_or_nctid}")
            if r.url:
                lines.append(f"**URL:** {r.url}")
            lines.append(f"**Relevance:** {r.relevance_score:.2f}")
            if r.summary:
                lines.append(f"\n{r.summary}")
            lines.append("")

        lines.append(f"\n**Disclaimer:** {MEDICAL_DISCLAIMER}")
        return "\n".join(lines)

    def _convert_results(
        self,
        raw_results: list[dict[str, Any]],
        default_source: str = "pubmed",
    ) -> list[ClinicalResearchResult]:
        """Convert raw ingest results into ClinicalResearchResult models."""
        results: list[ClinicalResearchResult] = []
        for item in raw_results:
            source = item.get("_source", item.get("source", default_source))
            # Normalize source to allowed values
            if source not in ("pubmed", "clinicaltrials"):
                source = default_source

            pmid_or_nctid = item.get(
                "pmid",
                item.get("nctid", item.get("id", item.get("document_id", ""))),
            )

            url = item.get("url", "")
            if not url and pmid_or_nctid:
                if source == "pubmed":
                    url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid_or_nctid}/"
                elif source == "clinicaltrials":
                    url = f"https://clinicaltrials.gov/study/{pmid_or_nctid}"

            results.append(
                ClinicalResearchResult(
                    title=item.get("title", "Untitled"),
                    source=source,
                    summary=item.get(
                        "content",
                        item.get("text", item.get("abstract", "")),
                    ),
                    relevance_score=float(
                        item.get("score", item.get("relevance_score", 0))
                    ),
                    pmid_or_nctid=str(pmid_or_nctid),
                    url=url,
                )
            )

        # Rank by relevance descending
        results.sort(key=lambda r: r.relevance_score, reverse=True)
        return results
