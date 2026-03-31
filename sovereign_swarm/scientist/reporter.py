"""Research report generation from completed research cycles."""

from __future__ import annotations

from typing import Any

import structlog

from sovereign_swarm.scientist.models import (
    HypothesisStatus,
    ResearchCycle,
    ResearchReport,
)

logger = structlog.get_logger()


class ReportGenerator:
    def __init__(self, config: Any | None = None):
        self.config = config

    async def generate(self, cycle: ResearchCycle) -> ResearchReport:
        """Generate a structured research report from a completed cycle."""
        # Deduplicate citations across all results
        all_citations: dict[str, dict] = {}
        for result in cycle.results:
            for cite in result.citations:
                doc_id = cite.get("document_id", "")
                if doc_id and doc_id not in all_citations:
                    all_citations[doc_id] = cite

        # Build report sections
        abstract = self._generate_abstract(cycle)
        conclusion = self._generate_conclusion(cycle)

        report = ResearchReport(
            title=f"Research Report: {cycle.research_question}",
            research_question=cycle.research_question,
            abstract=abstract,
            hypotheses=cycle.hypotheses,
            experiments=cycle.experiments,
            results=cycle.results,
            conclusion=conclusion,
            citations=list(all_citations.values()),
        )

        return report

    def _generate_abstract(self, cycle: ResearchCycle) -> str:
        supported = [
            h
            for h in cycle.hypotheses
            if h.status == HypothesisStatus.SUPPORTED
        ]
        refuted = [
            h
            for h in cycle.hypotheses
            if h.status == HypothesisStatus.REFUTED
        ]

        parts = [f"This report investigates: {cycle.research_question}"]
        parts.append(
            f"We tested {len(cycle.hypotheses)} hypotheses through "
            f"{len(cycle.experiments)} experiments."
        )
        if supported:
            parts.append(
                "Evidence supports: "
                + "; ".join(h.statement[:100] for h in supported)
            )
        if refuted:
            parts.append(
                "Evidence refutes: "
                + "; ".join(h.statement[:100] for h in refuted)
            )

        unique_sources = set()
        for r in cycle.results:
            for c in r.citations:
                doc_id = c.get("document_id", "")
                if doc_id:
                    unique_sources.add(doc_id)
        parts.append(f"Based on {len(unique_sources)} unique sources.")

        return " ".join(parts)

    def _generate_conclusion(self, cycle: ResearchCycle) -> str:
        verdicts = []
        for h in cycle.hypotheses:
            verdicts.append(
                f"- {h.statement}: **{h.status.value}** "
                f"(confidence: {h.confidence:.0%})"
            )
        return "## Conclusions\n\n" + "\n".join(verdicts)

    def to_markdown(self, report: ResearchReport) -> str:
        """Convert report to full markdown document."""
        sections = [
            f"# {report.title}",
            f"\n*Generated: {report.generated_at.strftime('%Y-%m-%d %H:%M')}*\n",
            f"## Abstract\n\n{report.abstract}",
            f"\n## Research Question\n\n{report.research_question}",
            "\n## Hypotheses\n",
        ]

        for idx, h in enumerate(report.hypotheses, 1):
            sections.append(f"### H{idx}: {h.statement}")
            sections.append(f"- Status: **{h.status.value}**")
            sections.append(f"- Confidence: {h.confidence:.0%}")
            sections.append(f"- Rationale: {h.rationale}\n")

        sections.append("\n## Experiments\n")
        for exp in report.experiments:
            sections.append(f"### {exp.description}")
            sections.append(f"- Type: {exp.experiment_type.value}")
            sections.append(f"- Sources: {', '.join(exp.data_sources)}")
            sections.append(f"- Methodology:\n{exp.methodology}\n")

        sections.append("\n## Results\n")
        for result in report.results:
            sections.append("### Experiment Result")
            sections.append(
                f"- Supports hypothesis: {result.supports_hypothesis}"
            )
            sections.append(f"- Confidence: {result.confidence:.0%}")
            sections.append(
                f"- Interpretation: "
                f"{result.interpretation or 'See raw output'}\n"
            )

        sections.append(f"\n{report.conclusion}")

        if report.citations:
            sections.append("\n## References\n")
            for i, cite in enumerate(report.citations, 1):
                title = cite.get("title", "Unknown")
                source = cite.get("source", "")
                doc_id = cite.get("document_id", "")
                sections.append(
                    f"{i}. [{title}] (source: {source}, id: {doc_id})"
                )

        return "\n".join(sections)
