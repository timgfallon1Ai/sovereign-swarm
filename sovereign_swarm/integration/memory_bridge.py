"""Bridge to sovereign-ai's 3-tier memory system.

Falls back gracefully if sovereign-ai is not running.
"""

from __future__ import annotations

import sys

import structlog

logger = structlog.get_logger()


class MemoryBridge:
    """Bridge to sovereign-ai's 3-tier memory system.

    Falls back gracefully if sovereign-ai is not running.
    """

    def __init__(self, sovereign_ai_path: str = ""):
        self._available = False
        self._manager = None
        if sovereign_ai_path:
            sys.path.insert(0, sovereign_ai_path)
        try:
            from memory.manager import MemoryManager

            self._manager = MemoryManager
            self._available = True
            logger.info("memory_bridge.connected")
        except ImportError:
            logger.warning("memory_bridge.not_available")

    @property
    def available(self) -> bool:
        return self._available

    async def store_task_result(
        self,
        graph_id: str,
        node_id: str,
        agent_name: str,
        task: str,
        result: str,
    ) -> None:
        """Store task result as episodic memory."""
        if not self._available or self._manager is None:
            return
        try:
            manager = self._manager()
            await manager.store_interaction(
                interaction_type="AGENT_ACTION",
                content=f"[{agent_name}] {task}: {result[:500]}",
                metadata={
                    "graph_id": graph_id,
                    "node_id": node_id,
                    "agent": agent_name,
                    "source": "sovereign_swarm",
                },
            )
            logger.info(
                "memory_bridge.stored",
                agent=agent_name,
                graph_id=graph_id,
            )
        except Exception as e:
            logger.error("memory_bridge.store_failed", error=str(e))

    async def search_relevant(
        self, query: str, limit: int = 5
    ) -> list[dict]:
        """Search semantic memory for relevant context."""
        if not self._available or self._manager is None:
            return []
        try:
            manager = self._manager()
            results = await manager.search_memory(query=query, limit=limit)
            return results if isinstance(results, list) else []
        except Exception as e:
            logger.error("memory_bridge.search_failed", error=str(e))
            return []

    async def get_cognitive_profile(
        self, category: str = ""
    ) -> list[dict]:
        """Get learned preferences from cognitive profile."""
        if not self._available or self._manager is None:
            return []
        try:
            manager = self._manager()
            profile = await manager.get_cognitive_profile(category=category)
            return profile if isinstance(profile, list) else []
        except Exception as e:
            logger.error(
                "memory_bridge.cognitive_profile_failed", error=str(e)
            )
            return []
