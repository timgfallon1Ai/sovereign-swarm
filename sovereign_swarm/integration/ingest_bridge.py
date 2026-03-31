"""Bridge to sovereign-ingest knowledge base.

Imports tool functions directly from sovereign-ingest (same machine).
Falls back gracefully if sovereign-ingest is not installed.
"""

from __future__ import annotations

import sys

import structlog

logger = structlog.get_logger()


class SovereignIngestBridge:
    def __init__(self, ingest_path: str = ""):
        self._available = False
        if ingest_path:
            sys.path.insert(0, ingest_path)
        try:
            from sovereign_ingest.mcp_server import tools as ingest_tools

            self._tools = ingest_tools
            self._available = True
            logger.info("ingest_bridge.connected")
        except ImportError:
            logger.warning(
                "ingest_bridge.not_available", msg="sovereign-ingest not found"
            )

    @property
    def available(self) -> bool:
        return self._available

    async def search(
        self, query: str, source: str = "", limit: int = 10
    ) -> dict:
        if not self._available:
            return {"results": [], "total": 0}
        return await self._tools.ingest_search(
            query=query, source=source, limit=limit
        )

    async def advanced_search(
        self,
        query: str,
        source: str = "",
        strategy: str = "hybrid",
        limit: int = 5,
    ) -> dict:
        if not self._available:
            return {"results": [], "total": 0}
        return await self._tools.ingest_advanced_search(
            query=query, source=source, strategy=strategy, limit=limit
        )

    async def smart_search(
        self, query: str, source: str = "", limit: int = 10
    ) -> dict:
        if not self._available:
            return {"results": [], "total": 0}
        return await self._tools.ingest_smart_search(
            query=query, source=source, limit=limit
        )

    async def graph_search(
        self, query: str, entity_type: str = "", limit: int = 20
    ) -> dict:
        if not self._available:
            return {"results": []}
        return await self._tools.ingest_graph_search(
            query=query, entity_type=entity_type, limit=limit
        )

    async def graph_context(self, entity_name: str) -> dict:
        if not self._available:
            return {}
        return await self._tools.ingest_graph_context(entity_name=entity_name)

    async def graph_rag_search(
        self, query: str, source: str = "", limit: int = 10
    ) -> dict:
        if not self._available:
            return {"results": [], "total": 0}
        return await self._tools.ingest_graph_rag_search(
            query=query, source=source, limit=limit
        )

    async def get_document(
        self, document_id: str = "", title: str = ""
    ) -> dict:
        if not self._available:
            return {}
        return await self._tools.ingest_get_document(
            document_id=document_id, title=title
        )

    async def get_stats(self) -> dict:
        if not self._available:
            return {}
        return await self._tools.ingest_get_stats()

    async def inject_document(
        self,
        title: str,
        content: str,
        source: str,
        metadata: dict | None = None,
    ) -> bool:
        """Write a new document back into sovereign-ingest."""
        if not self._available:
            return False
        try:
            from sovereign_ingest.config import get_settings
            from sovereign_ingest.storage.file_store import FileStore

            settings = get_settings()
            settings.ensure_dirs(source)

            # Save to file store
            file_store = FileStore(settings.connector_raw_dir(source))
            category = (metadata or {}).get("category", "swarm_generated")
            file_store.save_document(
                document_id=f"swarm_{title[:50].replace(' ', '_').lower()}",
                source=source,
                category=category,
                title=title,
                content=content,
                metadata=metadata or {},
            )

            logger.info(
                "ingest_bridge.document_injected", title=title, source=source
            )
            return True
        except Exception as e:
            logger.error("ingest_bridge.inject_failed", error=str(e))
            return False

    async def update_knowledge_graph(
        self,
        entities: list[dict] | None = None,
        relationships: list[dict] | None = None,
    ) -> bool:
        """Push new entities/relationships to the knowledge graph."""
        if not self._available:
            return False
        try:
            from sovereign_ingest.config import get_settings
            from sovereign_ingest.knowledge_graph.graph_store import GraphStore

            settings = get_settings()
            graph_path = str(
                settings.data_dir / "knowledge_graph" / "graph.pkl"
            )
            store = GraphStore(graph_path)
            store.load()

            for e in entities or []:
                store.add_entity(e)
            for r in relationships or []:
                store.add_relationship(r)

            store.save()
            logger.info(
                "ingest_bridge.kg_updated",
                entities=len(entities or []),
                relationships=len(relationships or []),
            )
            return True
        except Exception as e:
            logger.error("ingest_bridge.kg_update_failed", error=str(e))
            return False
