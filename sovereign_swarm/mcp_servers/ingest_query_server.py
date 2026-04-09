"""sovereign_ingest_query_mcp — semantic search over sovereign-ingest ChromaDB.

Read-only MCP server that exposes the sovereign-ingest vector store
to external MCP clients (Accio Work, Claude Desktop, Cursor, etc.)
for grounding sourcing research, OEM supplier lookups, and any other
task that benefits from the 106k+ chunks already indexed across 22
connectors.

This server is deliberately **thin** — it opens a read-only
ChromaDB ``PersistentClient`` against the existing sovereign-ingest
collection (the one currently living on the T7 Shield via symlink)
and forwards queries via Chroma's native embedding function. No
writes, no deletes, no training, no trace data exported.

Exposed tools
-------------
- ``semantic_search``      — top-k semantic search across the whole KB.
- ``search_by_source``     — same, filtered to one source connector.
- ``list_sources``         — enumerate connector names present in the KB.
- ``collection_stats``     — total chunk count + per-source counts (top N).
- ``get_chunk``            — fetch a single chunk by document_id + chunk_index.

Run with:
    python -m sovereign_swarm.mcp_servers.ingest_query_server

Environment variables
---------------------
- ``SOVEREIGN_INGEST_CHROMA_PATH`` — override the ChromaDB persist dir.
  Default: ``/Volumes/T7_Shield/sovereign-data/sovereign-ingest/chroma``
  (with fallback to ``~/Documents/GitHub/sovereign-ingest/data/chroma``).
- ``SOVEREIGN_INGEST_COLLECTION``  — override collection name.
  Default: ``sovereign_ingest``.

The server fails gracefully to a status-code-only response if
ChromaDB is not importable or the persist dir doesn't exist — the
MCP client sees a structured error, not a crash.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

logger = logging.getLogger(__name__)

DEFAULT_CHROMA_PATHS = [
    "/Volumes/T7_Shield/sovereign-data/sovereign-ingest/chroma",
    "~/Documents/GitHub/sovereign-ingest/data/chroma",
]
DEFAULT_COLLECTION = "sovereign_ingest"


mcp = FastMCP(
    "sovereign-ingest-query",
    instructions=(
        "Read-only semantic search over the sovereign-ingest knowledge "
        "base (106k+ chunks across 22 connectors including arXiv, "
        "PubMed, OpenFDA, ClinicalTrials, NBER, Kronos, MetaOSINT, and "
        "more). Use these tools to ground any research / sourcing / "
        "marketing / technical question in Tim Fallon's curated corpus. "
        "Results are read-only; no writes possible."
    ),
)


# ---------------------------------------------------------------------------
# Lazy ChromaDB singleton
# ---------------------------------------------------------------------------


class _ChromaHandle:
    """Lazy-initialized ChromaDB handle.

    Holds a singleton client/collection pair. Fails closed with a
    descriptive error when ChromaDB isn't importable or the persist
    dir is missing; every tool wraps the handle access so the MCP
    client always gets a structured response.
    """

    def __init__(self) -> None:
        self._client = None
        self._collection = None
        self._persist_path: Path | None = None
        self._collection_name = os.environ.get(
            "SOVEREIGN_INGEST_COLLECTION", DEFAULT_COLLECTION
        )
        self._init_error: str | None = None

    def _resolve_path(self) -> Path | None:
        override = os.environ.get("SOVEREIGN_INGEST_CHROMA_PATH")
        if override:
            p = Path(os.path.expanduser(override))
            return p if p.exists() else None
        for cand in DEFAULT_CHROMA_PATHS:
            p = Path(os.path.expanduser(cand))
            if p.exists():
                return p
        return None

    def connect(self) -> tuple[Any, Any, str | None]:
        """Return (client, collection, error). error is None on success."""
        if self._collection is not None:
            return self._client, self._collection, None
        if self._init_error is not None:
            return None, None, self._init_error

        try:
            import chromadb  # type: ignore  # noqa: PLC0415
        except ImportError as exc:
            self._init_error = (
                "chromadb package not installed in the sovereign-swarm venv. "
                f"Install with: .venv/bin/pip install chromadb. Underlying: {exc}"
            )
            return None, None, self._init_error

        path = self._resolve_path()
        if path is None:
            self._init_error = (
                "sovereign-ingest ChromaDB not found. Set "
                "SOVEREIGN_INGEST_CHROMA_PATH or ensure one of "
                f"{DEFAULT_CHROMA_PATHS} exists."
            )
            return None, None, self._init_error

        try:
            self._persist_path = path
            self._client = chromadb.PersistentClient(path=str(path))
            self._collection = self._client.get_collection(self._collection_name)
        except Exception as exc:  # noqa: BLE001
            self._init_error = (
                f"ChromaDB connect failed (path={path}, "
                f"collection={self._collection_name}): "
                f"{type(exc).__name__}: {exc}"
            )
            return None, None, self._init_error
        return self._client, self._collection, None


_handle = _ChromaHandle()


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------


def _format_results(raw: dict, top_k: int) -> list[dict[str, Any]]:
    """Convert Chroma's query() response into a JSON-safe result list."""
    out: list[dict[str, Any]] = []
    ids = raw.get("ids") or []
    if not ids or not ids[0]:
        return out
    docs = (raw.get("documents") or [[]])[0]
    metas = (raw.get("metadatas") or [[]])[0]
    dists = (raw.get("distances") or [[]])[0]
    for i, chunk_id in enumerate(ids[0][:top_k]):
        meta = metas[i] if i < len(metas) else {}
        doc = docs[i] if i < len(docs) else ""
        dist = dists[i] if i < len(dists) else 0.0
        # Chroma distances are cosine (0..2); convert to a 0..1 similarity score
        score = max(0.0, 1.0 - (dist / 2.0))
        out.append(
            {
                "chunk_id": chunk_id,
                "document_id": meta.get("document_id", ""),
                "document_title": meta.get("title", ""),
                "source": meta.get("source", ""),
                "category": meta.get("category", ""),
                "chunk_index": meta.get("chunk_index", 0),
                "score": round(score, 4),
                "text": doc,
            }
        )
    return out


@mcp.tool()
async def semantic_search(
    query: str,
    top_k: int = 10,
) -> dict[str, Any]:
    """Top-k semantic search across the entire sovereign-ingest knowledge base.

    Searches ~106k chunks from 22 connectors (arXiv, PubMed, OpenFDA,
    ClinicalTrials, NBER, Kronos, MetaOSINT, etc.) via ChromaDB cosine
    similarity. Results are ordered by descending similarity score.

    Args:
        query: Natural-language query. Full sentences are fine.
        top_k: Max results to return (default 10, capped at 50).

    Returns a dict with ``results`` (list of chunk dicts with
    text/source/score/metadata) or an ``error`` string on failure.
    """
    top_k = max(1, min(int(top_k), 50))
    _, collection, err = _handle.connect()
    if err is not None:
        return {"error": err, "query": query}
    try:
        raw = collection.query(
            query_texts=[query],
            n_results=top_k,
            include=["documents", "metadatas", "distances"],
        )
    except Exception as exc:  # noqa: BLE001
        return {"error": f"chromadb query failed: {exc}", "query": query}
    return {
        "query": query,
        "top_k": top_k,
        "results": _format_results(raw, top_k),
    }


@mcp.tool()
async def search_by_source(
    query: str,
    source: str,
    top_k: int = 10,
) -> dict[str, Any]:
    """Semantic search filtered to one source connector.

    Args:
        query: Natural-language query.
        source: Exact connector name (e.g. ``arxiv``, ``pubmed``,
            ``openfda``, ``nber``, ``clinicaltrials``, ``metaosint``).
            Call ``list_sources`` first to see what's available.
        top_k: Max results (default 10, capped at 50).
    """
    top_k = max(1, min(int(top_k), 50))
    _, collection, err = _handle.connect()
    if err is not None:
        return {"error": err, "query": query, "source": source}
    try:
        raw = collection.query(
            query_texts=[query],
            n_results=top_k,
            where={"source": source},
            include=["documents", "metadatas", "distances"],
        )
    except Exception as exc:  # noqa: BLE001
        return {
            "error": f"chromadb query failed: {exc}",
            "query": query,
            "source": source,
        }
    return {
        "query": query,
        "source": source,
        "top_k": top_k,
        "results": _format_results(raw, top_k),
    }


@mcp.tool()
async def list_sources(limit: int = 50) -> dict[str, Any]:
    """Enumerate the distinct source connector names in the collection.

    Useful as a first call to discover what's available before running
    a filtered ``search_by_source``. Pulls a representative sample of
    metadata from the collection (Chroma has no native DISTINCT).
    """
    _, collection, err = _handle.connect()
    if err is not None:
        return {"error": err}
    try:
        # get() with no query returns up to `limit` items sampled from the front
        sample_limit = max(limit * 20, 500)
        raw = collection.get(limit=sample_limit, include=["metadatas"])
    except Exception as exc:  # noqa: BLE001
        return {"error": f"chromadb get failed: {exc}"}
    sources: dict[str, int] = {}
    for meta in raw.get("metadatas") or []:
        s = (meta or {}).get("source") or ""
        if not s:
            continue
        sources[s] = sources.get(s, 0) + 1
    ordered = sorted(sources.items(), key=lambda kv: kv[1], reverse=True)
    return {
        "sources": [{"source": s, "sample_count": c} for s, c in ordered[:limit]],
        "sample_size": sum(sources.values()),
        "note": (
            "Counts reflect a bounded sample (~10k chunks), not the "
            "full collection. Use collection_stats() for an exact "
            "top-N breakdown."
        ),
    }


@mcp.tool()
async def collection_stats(top_sources: int = 10) -> dict[str, Any]:
    """Return the total chunk count and the top-N most common sources.

    More expensive than ``list_sources`` because it pulls more metadata
    to get a better per-source count. Still bounded — very large
    collections return approximate counts rather than exact.
    """
    top_sources = max(1, min(int(top_sources), 50))
    _, collection, err = _handle.connect()
    if err is not None:
        return {"error": err}
    try:
        total = collection.count()
    except Exception as exc:  # noqa: BLE001
        return {"error": f"chromadb count failed: {exc}"}
    # Sample a larger slice to approximate per-source distribution
    try:
        sample_limit = min(total, 20000)
        raw = collection.get(limit=sample_limit, include=["metadatas"])
    except Exception as exc:  # noqa: BLE001
        return {
            "error": f"chromadb sample get failed: {exc}",
            "total_chunks": total,
        }
    sources: dict[str, int] = {}
    for meta in raw.get("metadatas") or []:
        s = (meta or {}).get("source") or ""
        if not s:
            continue
        sources[s] = sources.get(s, 0) + 1
    ordered = sorted(sources.items(), key=lambda kv: kv[1], reverse=True)
    return {
        "total_chunks": total,
        "top_sources": [
            {"source": s, "sampled_count": c} for s, c in ordered[:top_sources]
        ],
        "sample_size": len(raw.get("metadatas") or []),
    }


@mcp.tool()
async def get_chunk(
    document_id: str,
    chunk_index: int = 0,
) -> dict[str, Any]:
    """Retrieve a single chunk by its document_id + chunk_index.

    Use this after a semantic_search call when you need to pull
    additional context around a hit. Not intended for bulk retrieval.
    """
    _, collection, err = _handle.connect()
    if err is not None:
        return {"error": err}
    try:
        raw = collection.get(
            where={"document_id": document_id},
            include=["documents", "metadatas"],
            limit=50,
        )
    except Exception as exc:  # noqa: BLE001
        return {"error": f"chromadb get failed: {exc}", "document_id": document_id}
    metas = raw.get("metadatas") or []
    docs = raw.get("documents") or []
    for i, meta in enumerate(metas):
        if (meta or {}).get("chunk_index") == chunk_index:
            return {
                "document_id": document_id,
                "chunk_index": chunk_index,
                "text": docs[i] if i < len(docs) else "",
                "metadata": meta,
            }
    return {
        "error": "chunk not found",
        "document_id": document_id,
        "chunk_index": chunk_index,
        "matching_chunks": len(metas),
    }


def main() -> None:
    """Entry point for ``python -m sovereign_swarm.mcp_servers.ingest_query_server``."""
    mcp.run()


if __name__ == "__main__":
    main()
