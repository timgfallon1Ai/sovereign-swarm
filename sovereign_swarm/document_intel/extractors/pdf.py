"""PDF extraction -- uses PyPDF2/pdfplumber when available, stubs otherwise."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import structlog

from sovereign_swarm.document_intel.models import ExtractedContent

logger = structlog.get_logger()

# Optional dependencies -- degrade gracefully
try:
    import pdfplumber  # type: ignore[import-untyped]

    _HAS_PDFPLUMBER = True
except ImportError:
    _HAS_PDFPLUMBER = False

try:
    from PyPDF2 import PdfReader  # type: ignore[import-untyped]

    _HAS_PYPDF2 = True
except ImportError:
    _HAS_PYPDF2 = False


class PDFExtractor:
    """Extract text, tables, and metadata from PDF files."""

    def extract_text(self, path: str | Path) -> str:
        """Return the full text content of a PDF."""
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"PDF not found: {path}")

        if _HAS_PDFPLUMBER:
            return self._text_pdfplumber(path)
        if _HAS_PYPDF2:
            return self._text_pypdf2(path)

        logger.warning("pdf_extractor.no_library", path=str(path))
        return f"[STUB] PDF text extraction not available -- install pdfplumber or PyPDF2. Path: {path}"

    def extract_tables(self, path: str | Path) -> list[list[list[str]]]:
        """Return tables found in the PDF (list of tables, each a list of rows)."""
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"PDF not found: {path}")

        if _HAS_PDFPLUMBER:
            return self._tables_pdfplumber(path)

        logger.warning("pdf_extractor.tables_stub", path=str(path))
        return []

    def extract_metadata(self, path: str | Path) -> dict[str, Any]:
        """Return PDF metadata (author, title, creation date, etc.)."""
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"PDF not found: {path}")

        if _HAS_PYPDF2:
            return self._metadata_pypdf2(path)
        if _HAS_PDFPLUMBER:
            return self._metadata_pdfplumber(path)

        return {"stub": True, "path": str(path)}

    def extract_all(self, path: str | Path) -> ExtractedContent:
        """Full extraction -- text, tables, metadata."""
        path = Path(path)
        text = self.extract_text(path)
        tables = self.extract_tables(path)
        metadata = self.extract_metadata(path)
        page_count = metadata.get("page_count", 0)
        return ExtractedContent(
            text=text,
            tables=tables,
            metadata=metadata,
            page_count=page_count,
        )

    # ------------------------------------------------------------------
    # pdfplumber backends
    # ------------------------------------------------------------------

    @staticmethod
    def _text_pdfplumber(path: Path) -> str:
        pages: list[str] = []
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    pages.append(text)
        return "\n\n".join(pages)

    @staticmethod
    def _tables_pdfplumber(path: Path) -> list[list[list[str]]]:
        all_tables: list[list[list[str]]] = []
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                tables = page.extract_tables()
                if tables:
                    for table in tables:
                        cleaned = [
                            [cell or "" for cell in row] for row in table
                        ]
                        all_tables.append(cleaned)
        return all_tables

    @staticmethod
    def _metadata_pdfplumber(path: Path) -> dict[str, Any]:
        with pdfplumber.open(path) as pdf:
            meta = dict(pdf.metadata) if pdf.metadata else {}
            meta["page_count"] = len(pdf.pages)
        return meta

    # ------------------------------------------------------------------
    # PyPDF2 backends
    # ------------------------------------------------------------------

    @staticmethod
    def _text_pypdf2(path: Path) -> str:
        reader = PdfReader(str(path))
        pages: list[str] = []
        for page in reader.pages:
            text = page.extract_text()
            if text:
                pages.append(text)
        return "\n\n".join(pages)

    @staticmethod
    def _metadata_pypdf2(path: Path) -> dict[str, Any]:
        reader = PdfReader(str(path))
        meta: dict[str, Any] = {}
        if reader.metadata:
            for key, value in reader.metadata.items():
                meta[key.lstrip("/")] = str(value) if value else ""
        meta["page_count"] = len(reader.pages)
        return meta
