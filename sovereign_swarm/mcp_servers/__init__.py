"""Sovereign MCP servers — surfaces Sovereign capabilities to external MCP clients.

Three zero-trust, read-mostly MCP servers that any MCP client (Claude
Desktop, Cursor, Accio Work, etc.) can consume:

1. ``sovereign_brand_mcp`` — tenant brand lookups (read-only)
2. ``sovereign_ingest_query_mcp`` — ChromaDB semantic search (read-only)
3. ``sovereign_marketing_mcp`` — marketing ensemble dispatch (execution,
   gated by publish-approval handshake)

Each server is independently runnable via ``python -m
sovereign_swarm.mcp_servers.<name>`` and speaks stdio transport.

Design rules (non-negotiable):
- Each server is a thin adapter over existing sovereign-swarm code
  paths. No new business logic.
- Every tool is read-only OR gated by Sovereign's existing approval
  rules (e.g., PublishGate for the marketing server).
- No customer-zero trace data is ever emitted to a tool response.
- Fail-open: an MCP client calling a broken tool gets a structured
  error response, never an exception that crashes the server.
- Model-agnostic: the servers don't care which LLM is calling them.
  Accio Work, Claude Desktop, Cursor all work.
"""

__all__ = [
    "brand_server",
    "ingest_query_server",
    "marketing_server",
]
