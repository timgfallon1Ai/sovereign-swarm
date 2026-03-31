"""Core task execution engine — runs DAG nodes concurrently with learning."""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import TYPE_CHECKING, Any

import structlog

from sovereign_swarm.runtime.checkpoint import CheckpointManager
from sovereign_swarm.runtime.graph import TaskGraph
from sovereign_swarm.runtime.models import TaskNode, TaskStatus
from sovereign_swarm.protocol.registry import AgentRegistry
from sovereign_swarm.protocol.swarm_agent import SwarmAgentRequest

if TYPE_CHECKING:
    from sovereign_swarm.protocol.permissions import PermissionManager

logger = structlog.get_logger()


class TaskExecutor:
    """Execute a TaskGraph DAG respecting dependencies, concurrency, and learning."""

    def __init__(
        self,
        registry: AgentRegistry,
        checkpoint: CheckpointManager,
        fast_learner: Any | None = None,
        audit_logger: Any | None = None,
        permissions: PermissionManager | None = None,
        max_concurrency: int = 5,
    ) -> None:
        self.registry = registry
        self.checkpoint = checkpoint
        self.fast_learner = fast_learner
        self.audit = audit_logger
        self.permissions = permissions
        self._semaphore = asyncio.Semaphore(max_concurrency)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def execute_graph(self, graph: TaskGraph) -> TaskGraph:
        """Execute all nodes in the DAG respecting dependencies."""
        graph.model.status = TaskStatus.RUNNING
        await self.checkpoint.save(graph.model)

        logger.info(
            "executor.graph.start",
            graph_id=graph.model.id,
            node_count=len(graph.model.nodes),
        )

        while not graph.is_complete():
            ready = graph.get_ready_nodes()

            if not ready:
                # Check if we're deadlocked (no ready nodes but not complete)
                running = [
                    n
                    for n in graph.model.nodes.values()
                    if n.status == TaskStatus.RUNNING
                ]
                waiting = [
                    n
                    for n in graph.model.nodes.values()
                    if n.status == TaskStatus.WAITING_APPROVAL
                ]

                if not running and not waiting:
                    # True deadlock — mark remaining pending nodes as failed
                    logger.error(
                        "executor.graph.deadlock",
                        graph_id=graph.model.id,
                    )
                    for node in graph.model.nodes.values():
                        if node.status == TaskStatus.PENDING:
                            node.status = TaskStatus.FAILED
                            node.error = "Deadlocked — unmet dependencies"
                    break

                # Wait for running / waiting-approval nodes to complete
                await asyncio.sleep(0.1)
                continue

            # Execute ready nodes concurrently
            async with asyncio.TaskGroup() as tg:
                for node in ready:
                    node.status = TaskStatus.RUNNING
                    node.start_time = datetime.utcnow()
                    tg.create_task(self._execute_node(node, graph))

            await self.checkpoint.save(graph.model)

        # ------------------------------------------------------------------
        # Determine final graph status
        # ------------------------------------------------------------------
        failed = [
            n for n in graph.model.nodes.values() if n.status == TaskStatus.FAILED
        ]
        if failed:
            graph.model.status = TaskStatus.FAILED
        else:
            graph.model.status = TaskStatus.SUCCESS

        graph.model.completed_at = datetime.utcnow()
        await self.checkpoint.save(graph.model)

        logger.info(
            "executor.graph.complete",
            graph_id=graph.model.id,
            status=graph.model.status.value,
            summary=graph.get_status_summary(),
        )
        return graph

    # ------------------------------------------------------------------
    # Node execution
    # ------------------------------------------------------------------

    async def _execute_node(self, node: TaskNode, graph: TaskGraph) -> None:
        """Execute a single task node with learning integration."""
        async with self._semaphore:
            try:
                # 1. Get relevant skill patches from fast learner
                patches: list[Any] = []
                if self.fast_learner:
                    patches = self.fast_learner.get_patches_for_task(
                        node.assigned_agent, node.description
                    )

                # 2. Check permissions
                if self.permissions:
                    allowed, reason = self.permissions.check_permission(
                        node.assigned_agent, "execute", node.description
                    )
                    if not allowed:
                        node.status = TaskStatus.WAITING_APPROVAL
                        node.metadata["approval_reason"] = reason
                        logger.info(
                            "executor.node.needs_approval",
                            node_id=node.id,
                            agent=node.assigned_agent,
                            reason=reason,
                        )
                        return

                # 3. Get agent from registry
                agent = self.registry.get_agent(node.assigned_agent)
                if not agent:
                    raise RuntimeError(f"Agent '{node.assigned_agent}' not found in registry")

                # 4. Build request and execute
                request = SwarmAgentRequest(
                    task=node.description,
                    context=node.input_data,
                    parameters=node.metadata,
                    user_id=graph.model.user_id,
                    conversation_id=graph.model.conversation_id,
                    skill_patches=[
                        p.__dict__ if hasattr(p, "__dict__") else p for p in patches
                    ],
                )

                response = await asyncio.wait_for(
                    agent.execute_with_learning(request),
                    timeout=node.timeout_seconds,
                )

                # 5. Process result
                if response.status == "success":
                    node.status = TaskStatus.SUCCESS
                    node.output_data = {"output": response.output, "data": response.data}
                    node.end_time = datetime.utcnow()

                    # Fast-learn from success
                    if self.fast_learner and response.confidence >= 0.85:
                        await self.fast_learner.on_success(
                            node.assigned_agent,
                            node.description,
                            response.output,
                            response.confidence,
                        )

                    if self.audit:
                        await self.audit.log_task_complete(node, graph.model)

                    logger.info(
                        "executor.node.success",
                        node_id=node.id,
                        agent=node.assigned_agent,
                        confidence=response.confidence,
                    )

                elif response.status == "needs_approval":
                    node.status = TaskStatus.WAITING_APPROVAL
                    node.output_data = {"output": response.output}
                    logger.info(
                        "executor.node.needs_approval",
                        node_id=node.id,
                        agent=node.assigned_agent,
                    )

                else:
                    raise RuntimeError(
                        response.error or response.output or "Agent returned error status"
                    )

            except asyncio.TimeoutError:
                node.error = f"Timed out after {node.timeout_seconds}s"
                node.end_time = datetime.utcnow()
                self._handle_failure(node, graph)

            except Exception as e:
                node.error = str(e)
                node.end_time = datetime.utcnow()
                self._handle_failure(node, graph, e)

    # ------------------------------------------------------------------
    # Failure handling
    # ------------------------------------------------------------------

    def _handle_failure(
        self, node: TaskNode, graph: TaskGraph, exc: Exception | None = None
    ) -> None:
        """Handle a node failure: retry or mark failed, record learning."""
        error_str = node.error or str(exc) or "unknown error"

        # Fast-learn from failure
        if self.fast_learner:
            # Fire-and-forget; we're in sync context so schedule it
            asyncio.ensure_future(
                self.fast_learner.on_failure(
                    node.assigned_agent,
                    node.description,
                    error_str,
                    node.input_data,
                )
            )

        if node.retry_count < node.max_retries:
            node.retry_count += 1
            node.status = TaskStatus.PENDING  # Will be picked up on next loop iteration
            node.error = f"Retry {node.retry_count}/{node.max_retries}: {error_str}"
            logger.warning(
                "executor.node.retry",
                node_id=node.id,
                agent=node.assigned_agent,
                attempt=node.retry_count,
                error=error_str,
            )
        else:
            node.status = TaskStatus.FAILED
            logger.error(
                "executor.node.failed",
                node_id=node.id,
                agent=node.assigned_agent,
                error=error_str,
            )

        if self.audit:
            asyncio.ensure_future(
                self.audit.log_task_fail(node, graph.model, error_str)
            )
