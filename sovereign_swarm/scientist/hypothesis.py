"""Hypothesis generation using knowledge graph context."""

from __future__ import annotations

from typing import Any

import structlog

from sovereign_swarm.integration.ingest_bridge import SovereignIngestBridge
from sovereign_swarm.scientist.models import Hypothesis

logger = structlog.get_logger()


class HypothesisGenerator:
    def __init__(
        self,
        ingest_bridge: SovereignIngestBridge,
        config: Any | None = None,
    ):
        self.ingest = ingest_bridge
        self.config = config
        self._client: Any | None = None

    async def generate(
        self, question: str, max_hypotheses: int = 5
    ) -> list[Hypothesis]:
        """Generate testable hypotheses grounded in the knowledge graph."""
        # 1. Search knowledge graph for relevant context
        graph_results = await self.ingest.graph_rag_search(question, limit=10)
        graph_context = await self._build_graph_context(question)

        # 2. Search literature
        literature = await self.ingest.advanced_search(question, limit=10)

        # 3. Use Claude to generate hypotheses
        hypotheses = await self._generate_with_llm(
            question, graph_results, literature, graph_context, max_hypotheses
        )

        return hypotheses

    async def _build_graph_context(self, question: str) -> str:
        """Get knowledge graph context for key entities in the question."""
        entity_results = await self.ingest.graph_search(question, limit=5)
        contexts = []
        for entity in entity_results.get("results", [])[:3]:
            ctx = await self.ingest.graph_context(entity.get("name", ""))
            if ctx:
                contexts.append(
                    f"Entity: {entity.get('name')}\n"
                    f"{self._format_context(ctx)}"
                )
        return "\n\n".join(contexts)

    async def _generate_with_llm(
        self,
        question: str,
        graph_results: dict,
        literature: dict,
        graph_context: str,
        max_h: int,
    ) -> list[Hypothesis]:
        """Use Claude to generate hypotheses, falling back to search-based."""
        client = self._get_client()
        if not client:
            return self._fallback_hypotheses(
                question, graph_results, literature, max_h
            )

        # Build context from search results
        lit_context = "\n".join(
            f"- [{r.get('source', '?')}] {r.get('document_title', '?')}: "
            f"{r.get('chunk_text', '')[:200]}"
            for r in literature.get("results", [])[:10]
        )
        graph_lit = "\n".join(
            f"- {r.get('document_title', '?')}: {r.get('chunk_text', '')[:200]}"
            for r in graph_results.get("results", [])[:10]
        )

        prompt = (
            f"Research question: {question}\n\n"
            f"## Knowledge Graph Context\n{graph_context or 'None available'}\n\n"
            f"## Literature\n{lit_context or 'None found'}\n\n"
            f"## Graph-augmented Results\n{graph_lit or 'None found'}\n\n"
            f"Generate up to {max_h} testable hypotheses. For each, provide:\n"
            f"1. A clear, testable statement\n"
            f"2. Rationale grounded in the evidence above\n"
            f"3. Key entities from the knowledge graph that are relevant\n\n"
            f"Format each as:\n"
            f"HYPOTHESIS: <statement>\n"
            f"RATIONALE: <reasoning>\n"
            f"ENTITIES: <comma-separated entity names>\n"
            f"---"
        )

        try:
            from sovereign_swarm.config import get_settings

            settings = get_settings()
            resp = await client.messages.create(
                model=settings.slow_model,
                max_tokens=2000,
                messages=[{"role": "user", "content": prompt}],
            )
            text = resp.content[0].text
            return self._parse_hypotheses(text)
        except Exception as e:
            logger.error("hypothesis.llm_failed", error=str(e))
            return self._fallback_hypotheses(
                question, graph_results, literature, max_h
            )

    def _parse_hypotheses(self, text: str) -> list[Hypothesis]:
        """Parse LLM output into Hypothesis objects."""
        hypotheses = []
        blocks = text.split("---")
        for block in blocks:
            block = block.strip()
            if not block:
                continue
            statement = ""
            rationale = ""
            entities: list[str] = []
            for line in block.split("\n"):
                line = line.strip()
                if line.upper().startswith("HYPOTHESIS:"):
                    statement = line.split(":", 1)[1].strip()
                elif line.upper().startswith("RATIONALE:"):
                    rationale = line.split(":", 1)[1].strip()
                elif line.upper().startswith("ENTITIES:"):
                    raw = line.split(":", 1)[1].strip()
                    entities = [e.strip() for e in raw.split(",") if e.strip()]
            if statement:
                hypotheses.append(
                    Hypothesis(
                        statement=statement,
                        rationale=rationale or "Generated from knowledge base",
                        knowledge_graph_entities=entities,
                    )
                )
        return hypotheses

    def _fallback_hypotheses(
        self,
        question: str,
        graph_results: dict,
        literature: dict,
        max_h: int,
    ) -> list[Hypothesis]:
        """Generate simple hypotheses from search result titles."""
        hypotheses = []
        seen: set[str] = set()

        for r in literature.get("results", [])[:max_h]:
            title = r.get("document_title", "")
            if title and title not in seen:
                seen.add(title)
                hypotheses.append(
                    Hypothesis(
                        statement=f"Evidence in '{title}' supports aspects of: {question}",
                        rationale=f"Based on document from {r.get('source', 'knowledge base')}",
                        supporting_evidence=[r.get("document_id", "")],
                    )
                )

        if not hypotheses:
            hypotheses.append(
                Hypothesis(
                    statement=f"The knowledge base contains relevant information about: {question}",
                    rationale="Default hypothesis when no specific evidence is found",
                )
            )

        return hypotheses[:max_h]

    def _get_client(self) -> Any | None:
        if self._client is None:
            try:
                import anthropic

                from sovereign_swarm.config import get_settings

                settings = get_settings()
                if settings.anthropic_api_key:
                    self._client = anthropic.AsyncAnthropic(
                        api_key=settings.anthropic_api_key
                    )
            except Exception:
                pass
        return self._client

    def _format_context(self, ctx: dict) -> str:
        """Format entity context for prompt."""
        parts = []
        for rel in ctx.get("outgoing", [])[:5]:
            parts.append(
                f"  -> {rel.get('type', '?')}: {rel.get('target', '?')}"
            )
        return "\n".join(parts)
