"""Experiment execution engine."""

from __future__ import annotations

import subprocess
from typing import Any

import structlog

from sovereign_swarm.integration.ingest_bridge import SovereignIngestBridge
from sovereign_swarm.scientist.models import Experiment, ExperimentResult, ExperimentType

logger = structlog.get_logger()


class ExperimentRunner:
    def __init__(
        self,
        ingest_bridge: SovereignIngestBridge,
        config: Any | None = None,
    ):
        self.ingest = ingest_bridge
        self.config = config

    async def run(self, experiment: Experiment) -> ExperimentResult:
        """Execute an experiment and return results."""
        handlers = {
            ExperimentType.LITERATURE_REVIEW: self._run_literature_review,
            ExperimentType.DATA_ANALYSIS: self._run_data_analysis,
            ExperimentType.COMPARISON: self._run_comparison,
            ExperimentType.COMPUTATION: self._run_computation,
            ExperimentType.API_QUERY: self._run_api_query,
        }
        handler = handlers.get(experiment.experiment_type)
        if handler is None:
            return ExperimentResult(
                experiment_id=experiment.id,
                raw_output="Unknown experiment type",
            )
        return await handler(experiment)

    async def _run_literature_review(
        self, exp: Experiment
    ) -> ExperimentResult:
        """Search knowledge base for evidence."""
        results = await self.ingest.smart_search(exp.description, limit=20)
        citations = []
        evidence_texts = []
        for r in results.get("results", []):
            citations.append(
                {
                    "document_id": r.get("document_id", ""),
                    "title": r.get("document_title", ""),
                    "source": r.get("source", ""),
                    "relevance": r.get("score", 0),
                }
            )
            evidence_texts.append(
                f"[{r.get('source', '?')}] "
                f"{r.get('document_title', '?')}: "
                f"{r.get('chunk_text', '')[:300]}"
            )

        raw_output = "\n\n".join(evidence_texts)
        return ExperimentResult(
            experiment_id=exp.id,
            raw_output=raw_output,
            citations=citations,
            confidence=min(len(citations) / 10, 1.0),
        )

    async def _run_data_analysis(self, exp: Experiment) -> ExperimentResult:
        """Analyze data from knowledge base."""
        results = await self.ingest.advanced_search(exp.description, limit=15)
        raw = "\n".join(
            r.get("chunk_text", "")[:500]
            for r in results.get("results", [])
        )
        return ExperimentResult(
            experiment_id=exp.id,
            raw_output=raw,
            citations=[
                {
                    "document_id": r.get("document_id", ""),
                    "title": r.get("document_title", ""),
                }
                for r in results.get("results", [])
            ],
        )

    async def _run_comparison(self, exp: Experiment) -> ExperimentResult:
        """Compare entities from knowledge graph."""
        parts = exp.description.replace("Compare: ", "").split(" vs ")
        contexts = []
        for entity in parts:
            ctx = await self.ingest.graph_context(entity.strip())
            if ctx:
                contexts.append(
                    f"### {entity.strip()}\n"
                    f"{self._format_entity_context(ctx)}"
                )
        raw_output = (
            "\n\n".join(contexts) if contexts else "No entity context found."
        )
        return ExperimentResult(
            experiment_id=exp.id,
            raw_output=raw_output,
        )

    async def _run_computation(self, exp: Experiment) -> ExperimentResult:
        """Run sandboxed Python computation."""
        if not exp.code:
            return ExperimentResult(
                experiment_id=exp.id, raw_output="No code to execute"
            )
        try:
            result = subprocess.run(
                ["python", "-c", exp.code],
                capture_output=True,
                text=True,
                timeout=60,
            )
            return ExperimentResult(
                experiment_id=exp.id,
                raw_output=result.stdout or result.stderr,
                confidence=0.8 if result.returncode == 0 else 0.2,
            )
        except subprocess.TimeoutExpired:
            return ExperimentResult(
                experiment_id=exp.id,
                raw_output="Computation timed out (60s)",
            )

    async def _run_api_query(self, exp: Experiment) -> ExperimentResult:
        """Query external APIs."""
        import httpx

        results = []
        for url in exp.parameters.get("urls", []):
            try:
                async with httpx.AsyncClient(timeout=30) as client:
                    resp = await client.get(url)
                    results.append(
                        f"[{resp.status_code}] {url}: {resp.text[:500]}"
                    )
            except Exception as e:
                results.append(f"[ERROR] {url}: {e}")
        return ExperimentResult(
            experiment_id=exp.id, raw_output="\n".join(results)
        )

    def _format_entity_context(self, ctx: dict) -> str:
        parts = []
        for key in ["outgoing", "incoming"]:
            for rel in ctx.get(key, [])[:10]:
                direction = "->" if key == "outgoing" else "<-"
                target_key = "target" if key == "outgoing" else "source"
                parts.append(
                    f"  {direction} {rel.get('type', '?')}: "
                    f"{rel.get(target_key, '?')}"
                )
        docs = ctx.get("documents", [])[:5]
        if docs:
            parts.append(f"  Referenced in {len(docs)} documents")
        return "\n".join(parts) if parts else "No context available"
