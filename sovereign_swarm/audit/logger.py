"""Structured audit logging for swarm operations."""

from __future__ import annotations

import structlog

from sovereign_swarm.audit.models import AuditEntry
from sovereign_swarm.audit.store import AuditStore
from sovereign_swarm.runtime.models import TaskGraphModel, TaskNode

logger = structlog.get_logger()


class AuditLogger:
    """Logs audit events via structlog and persists to AuditStore."""

    def __init__(self, store: AuditStore) -> None:
        self._store = store

    async def log(self, entry: AuditEntry) -> None:
        """Log an entry to both structlog and the persistent store."""
        logger.info(
            "audit.event",
            event_type=entry.event_type,
            agent=entry.agent_name,
            action=entry.action,
            graph_id=entry.graph_id,
            node_id=entry.node_id,
            status=entry.status,
        )
        await self._store.store(entry)

    async def log_task_start(self, node: TaskNode, graph: TaskGraphModel) -> None:
        await self.log(
            AuditEntry(
                event_type="task_start",
                agent_name=node.assigned_agent,
                action=f"started:{node.name}",
                graph_id=graph.id,
                node_id=node.id,
                user_id=graph.user_id,
                input_summary=str(node.input_data)[:500],
                status="running",
            )
        )

    async def log_task_complete(self, node: TaskNode, graph: TaskGraphModel) -> None:
        await self.log(
            AuditEntry(
                event_type="task_complete",
                agent_name=node.assigned_agent,
                action=f"completed:{node.name}",
                graph_id=graph.id,
                node_id=node.id,
                user_id=graph.user_id,
                output_summary=str(node.output_data)[:500],
                status="success",
            )
        )

    async def log_task_fail(
        self, node: TaskNode, graph: TaskGraphModel, error: str
    ) -> None:
        await self.log(
            AuditEntry(
                event_type="task_fail",
                agent_name=node.assigned_agent,
                action=f"failed:{node.name}",
                graph_id=graph.id,
                node_id=node.id,
                user_id=graph.user_id,
                output_summary=error[:500],
                status="failed",
            )
        )

    async def log_patch_applied(
        self, patch: dict, node: TaskNode
    ) -> None:
        await self.log(
            AuditEntry(
                event_type="patch_applied",
                agent_name=node.assigned_agent,
                action=f"applied_patch:{patch.get('id', 'unknown')}",
                node_id=node.id,
                status="applied",
                metadata={"patch_confidence": patch.get("confidence", 0)},
            )
        )

    async def log_approval_request(self, node: TaskNode) -> None:
        await self.log(
            AuditEntry(
                event_type="approval_request",
                agent_name=node.assigned_agent,
                action=f"needs_approval:{node.name}",
                node_id=node.id,
                status="waiting_approval",
            )
        )
