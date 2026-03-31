"""Adapts sovereign-ai's TaskPlan into sovereign-swarm's TaskGraph.

This is the bridge that activates the dormant depends_on field
in sovereign-ai's TaskStep, turning sequential execution into
parallel DAG execution.
"""

from __future__ import annotations

from typing import Any

import structlog

from sovereign_swarm.protocol.registry import AgentRegistry
from sovereign_swarm.runtime.coordinator import SwarmCoordinator
from sovereign_swarm.runtime.graph import TaskGraph
from sovereign_swarm.runtime.models import TaskGraphModel, TaskNode, TaskStatus

logger = structlog.get_logger()


class SupervisorAdapter:
    """Adapts sovereign-ai's TaskPlan into sovereign-swarm's TaskGraph.

    This is the bridge that activates the dormant depends_on field
    in sovereign-ai's TaskStep, turning sequential execution into
    parallel DAG execution.
    """

    def __init__(
        self, coordinator: SwarmCoordinator, registry: AgentRegistry
    ) -> None:
        self.coordinator = coordinator
        self.registry = registry

    async def execute_plan(
        self,
        plan: Any,
        message: str,
        intent: Any = None,
        user_id: str = "",
        conversation_id: str = "",
    ) -> list[dict]:
        """Convert TaskPlan steps into TaskGraph and execute via swarm.

        Returns results in the same format sovereign-ai's synthesizer expects:
        [{"agent": name, "status": status, "output": text, "data": dict}]
        """
        model = TaskGraphModel(
            name=f"plan_{conversation_id or 'adhoc'}",
            goal=message,
            user_id=user_id,
            conversation_id=conversation_id,
        )
        graph = TaskGraph(model)

        # Map step numbers to node IDs for dependency resolution
        step_to_node: dict[int, str] = {}

        for step in plan.steps:
            node = TaskNode(
                name=f"step_{step.step_number}",
                description=step.description,
                assigned_agent=step.target_agent,
                requires_approval=getattr(step, "requires_approval", False),
                input_data={
                    "message": message,
                    "intent": str(intent) if intent else "",
                },
            )
            graph.add_node(node)
            step_to_node[step.step_number] = node.id

            # Wire up dependencies from depends_on
            for dep_step in getattr(step, "depends_on", None) or []:
                dep_node_id = step_to_node.get(dep_step)
                if dep_node_id:
                    graph.add_dependency(node.id, dep_node_id)

        if not graph.validate():
            # Fallback: execute sequentially if DAG is invalid
            logger.warning(
                "supervisor_adapter.invalid_dag",
                msg="Falling back to sequential execution",
            )
            node_ids = list(graph.model.nodes.keys())
            for i in range(1, len(node_ids)):
                graph.add_dependency(node_ids[i], node_ids[i - 1])

        # Execute
        result_graph = await self.coordinator.executor.execute_graph(graph)

        # Convert results to the format sovereign-ai expects
        results = []
        for node in result_graph.model.nodes.values():
            results.append(
                {
                    "agent": node.assigned_agent,
                    "status": node.status.value,
                    "output": node.output_data.get("output", ""),
                    "data": node.output_data.get("data", {}),
                    "error": node.error,
                }
            )

        return results
