"""DocumentIntelAgent -- document intelligence for the Sovereign AI swarm."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import structlog

from sovereign_swarm.protocol.swarm_agent import (
    SwarmAgent,
    SwarmAgentCard,
    SwarmAgentRequest,
    SwarmAgentResponse,
)

logger = structlog.get_logger()


class DocumentIntelAgent(SwarmAgent):
    """Extracts, compares, and summarizes documents."""

    def __init__(self, config: Any | None = None) -> None:
        self.config = config
        self._pdf_extractor: Any | None = None
        self._docx_extractor: Any | None = None
        self._comparator: Any | None = None
        self._summarizer: Any | None = None

    @property
    def card(self) -> SwarmAgentCard:
        return SwarmAgentCard(
            name="document_intel",
            description=(
                "Document intelligence agent -- extracts text and tables, "
                "compares documents, summarizes content, finds entities and action items"
            ),
            domains=["document", "pdf", "contract", "invoice", "report"],
            supported_intents=[
                "extract_text",
                "extract_tables",
                "compare_documents",
                "summarize",
                "find_entities",
                "extract_action_items",
            ],
            capabilities=[
                "extract_text",
                "extract_tables",
                "compare_documents",
                "summarize",
                "find_entities",
                "extract_action_items",
            ],
        )

    async def execute(self, request: SwarmAgentRequest) -> SwarmAgentResponse:
        """Route document requests to the appropriate handler."""
        task = request.task.lower()

        try:
            if "compare" in task or "diff" in task:
                result = await self._handle_compare(request)
            elif "summar" in task:
                result = await self._handle_summarize(request)
            elif "table" in task:
                result = await self._handle_extract_tables(request)
            elif "action" in task and "item" in task:
                result = await self._handle_action_items(request)
            elif "entit" in task:
                result = await self._handle_entities(request)
            else:
                result = await self._handle_extract_text(request)

            return SwarmAgentResponse(
                agent_name="document_intel",
                status="success",
                output=result.get("markdown", str(result)),
                data=result,
                confidence=0.85,
            )
        except Exception as e:
            logger.error("document_intel.execute_failed", error=str(e))
            return SwarmAgentResponse(
                agent_name="document_intel",
                status="error",
                error=str(e),
            )

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------

    async def _handle_extract_text(self, request: SwarmAgentRequest) -> dict:
        path = request.parameters.get("path", "")
        if not path:
            return {"markdown": "No document path provided.", "text": ""}

        extractor = self._get_extractor(path)
        text = extractor.extract_text(path)
        return {
            "markdown": f"## Extracted Text\n\n{text[:2000]}{'...' if len(text) > 2000 else ''}",
            "text": text,
            "char_count": len(text),
        }

    async def _handle_extract_tables(self, request: SwarmAgentRequest) -> dict:
        path = request.parameters.get("path", "")
        if not path:
            return {"markdown": "No document path provided.", "tables": []}

        extractor = self._get_extractor(path)
        tables = extractor.extract_tables(path)
        lines = [f"## Extracted Tables: {len(tables)} found\n"]
        for i, table in enumerate(tables, 1):
            lines.append(f"### Table {i}")
            for row in table[:5]:
                lines.append("| " + " | ".join(row) + " |")
            if len(table) > 5:
                lines.append(f"... and {len(table) - 5} more rows")
            lines.append("")

        return {"markdown": "\n".join(lines), "tables": tables}

    async def _handle_compare(self, request: SwarmAgentRequest) -> dict:
        path_a = request.parameters.get("path_a", "")
        path_b = request.parameters.get("path_b", "")
        if not path_a or not path_b:
            return {"markdown": "Two document paths required (path_a, path_b)."}

        ext_a = self._get_extractor(path_a)
        ext_b = self._get_extractor(path_b)
        text_a = ext_a.extract_text(path_a)
        text_b = ext_b.extract_text(path_b)

        comparator = self._get_comparator()
        comparison = comparator.compare(text_a, text_b, label_a=path_a, label_b=path_b)

        lines = [
            f"## Document Comparison",
            f"**Similarity**: {comparison.similarity_score:.1%}",
            f"**Additions**: {len(comparison.additions)}",
            f"**Deletions**: {len(comparison.deletions)}",
            f"**Modifications**: {len(comparison.modifications)}",
        ]
        return {
            "markdown": "\n".join(lines),
            "comparison": comparison.model_dump(),
        }

    async def _handle_summarize(self, request: SwarmAgentRequest) -> dict:
        path = request.parameters.get("path", "")
        text = request.parameters.get("text", "")

        if path and not text:
            extractor = self._get_extractor(path)
            text = extractor.extract_text(path)

        if not text:
            return {"markdown": "No text to summarize."}

        summarizer = self._get_summarizer()
        summary = summarizer.summarize(text, title=request.parameters.get("title", ""))

        lines = [
            f"## Summary: {summary.title}\n",
            "**Key Points:**",
        ]
        for point in summary.key_points:
            lines.append(f"- {point}")

        if summary.action_items:
            lines.append("\n**Action Items:**")
            for item in summary.action_items:
                lines.append(f"- [ ] {item}")

        if summary.dates:
            lines.append(f"\n**Dates mentioned**: {', '.join(summary.dates[:5])}")
        if summary.amounts:
            lines.append(f"**Amounts mentioned**: {', '.join(summary.amounts[:5])}")

        return {
            "markdown": "\n".join(lines),
            "summary": summary.model_dump(),
        }

    async def _handle_entities(self, request: SwarmAgentRequest) -> dict:
        path = request.parameters.get("path", "")
        text = request.parameters.get("text", "")

        if path and not text:
            extractor = self._get_extractor(path)
            text = extractor.extract_text(path)

        if not text:
            return {"markdown": "No text to analyse."}

        summarizer = self._get_summarizer()
        summary = summarizer.summarize(text)
        return {
            "markdown": f"## Entities Found: {len(summary.entities)}\n"
            + "\n".join(f"- {e}" for e in summary.entities),
            "entities": summary.entities,
        }

    async def _handle_action_items(self, request: SwarmAgentRequest) -> dict:
        path = request.parameters.get("path", "")
        text = request.parameters.get("text", "")

        if path and not text:
            extractor = self._get_extractor(path)
            text = extractor.extract_text(path)

        if not text:
            return {"markdown": "No text to analyse."}

        summarizer = self._get_summarizer()
        summary = summarizer.summarize(text)
        return {
            "markdown": f"## Action Items: {len(summary.action_items)}\n"
            + "\n".join(f"- [ ] {item}" for item in summary.action_items),
            "action_items": summary.action_items,
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_extractor(self, path: str) -> Any:
        """Return the appropriate extractor based on file extension."""
        ext = Path(path).suffix.lower()
        if ext == ".pdf":
            return self._get_pdf_extractor()
        elif ext in (".docx", ".doc"):
            return self._get_docx_extractor()
        else:
            # Default to PDF extractor for unknown types
            return self._get_pdf_extractor()

    def _get_pdf_extractor(self):
        if self._pdf_extractor is None:
            from sovereign_swarm.document_intel.extractors.pdf import PDFExtractor

            self._pdf_extractor = PDFExtractor()
        return self._pdf_extractor

    def _get_docx_extractor(self):
        if self._docx_extractor is None:
            from sovereign_swarm.document_intel.extractors.docx import DocxExtractor

            self._docx_extractor = DocxExtractor()
        return self._docx_extractor

    def _get_comparator(self):
        if self._comparator is None:
            from sovereign_swarm.document_intel.comparator import DocumentComparator

            self._comparator = DocumentComparator()
        return self._comparator

    def _get_summarizer(self):
        if self._summarizer is None:
            from sovereign_swarm.document_intel.summarizer import DocumentSummarizer

            self._summarizer = DocumentSummarizer()
        return self._summarizer
