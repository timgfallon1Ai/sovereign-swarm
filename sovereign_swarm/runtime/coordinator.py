"""Swarm coordinator — accepts goals, decomposes into DAGs, executes."""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import Any

import structlog

from sovereign_swarm.runtime.checkpoint import CheckpointManager
from sovereign_swarm.runtime.executor import TaskExecutor
from sovereign_swarm.runtime.graph import TaskGraph
from sovereign_swarm.runtime.models import TaskGraphModel, TaskNode, TaskStatus
from sovereign_swarm.protocol.registry import AgentRegistry

logger = structlog.get_logger()

DECOMPOSITION_SYSTEM_PROMPT = """\
You are a task decomposition engine for a multi-agent swarm.
Given a user goal and a list of available agents, break the goal into
discrete task nodes that can be executed by the agents.

Respond with a JSON array of task objects. Each object must have:
- "name": short task name
- "description": what the agent should do (be specific)
- "assigned_agent": name of the agent to handle it (must match an available agent exactly)
- "dependencies": array of task names this depends on (empty if no dependencies)

Rules:
- Maximise parallelism: only add dependencies where output is genuinely required.
- Each task should be assigned to exactly one agent.
- If no agent matches a sub-task, assign it to the best-fit agent anyway.
- Return ONLY the JSON array, no markdown fences, no commentary.
"""


class SwarmCoordinator:
    """Accepts high-level goals, decomposes them into DAGs, and executes."""

    def __init__(
        self,
        executor: TaskExecutor,
        registry: AgentRegistry,
        checkpoint: CheckpointManager,
        config: dict[str, Any] | None = None,
    ) -> None:
        self.executor = executor
        self.registry = registry
        self.checkpoint = checkpoint
        self._config = config or {}
        self._model = self._config.get("coordinator_model", "claude-sonnet-4-6-20250514")

    @classmethod
    def with_defaults(
        cls,
        checkpoint_db: str | Path | None = None,
        config: dict[str, Any] | None = None,
        max_concurrency: int = 5,
    ) -> "SwarmCoordinator":
        """Build a fully-wired SwarmCoordinator with the default agent lineup.

        This is the one-liner entry point for any consumer (CLI, tests,
        external integrations) that just wants a working swarm without
        having to hand-construct the registry/executor/checkpoint chain.

        The registry is populated by ``bootstrap_default_registry()``, which
        loads every production agent that can be imported — including the
        vision-capable ``web_agent`` (UI-TARS-1.5-7B-4bit MLX). Agents with
        missing optional dependencies are skipped with a debug log line
        rather than failing the whole bootstrap.
        """
        from sovereign_swarm.protocol.registry import bootstrap_default_registry

        registry = bootstrap_default_registry()
        checkpoint = CheckpointManager(
            db_path=checkpoint_db or "data/checkpoints.db"
        )
        executor = TaskExecutor(
            registry=registry,
            checkpoint=checkpoint,
            max_concurrency=max_concurrency,
        )
        return cls(
            executor=executor,
            registry=registry,
            checkpoint=checkpoint,
            config=config,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def submit_goal(
        self,
        goal: str,
        user_id: str = "",
        conversation_id: str = "",
    ) -> TaskGraph:
        """Decompose a goal into a DAG and execute it."""
        logger.info("coordinator.submit_goal", goal=goal, user_id=user_id)

        graph = await self._decompose_goal(goal, user_id, conversation_id)

        if not graph.validate():
            logger.error("coordinator.invalid_graph", graph_id=graph.model.id)
            graph.model.status = TaskStatus.FAILED
            await self.checkpoint.save(graph.model)
            return graph

        result = await self.executor.execute_graph(graph)
        return result

    async def get_status(self, graph_id: str) -> dict | None:
        """Retrieve the persisted state of a graph."""
        return await self.checkpoint.load(graph_id)

    async def cancel(self, graph_id: str) -> None:
        """Cancel an in-progress graph."""
        data = await self.checkpoint.load(graph_id)
        if data is None:
            logger.warning("coordinator.cancel.not_found", graph_id=graph_id)
            return

        model = TaskGraphModel.model_validate(data)
        for node in model.nodes.values():
            if node.status in (TaskStatus.PENDING, TaskStatus.RUNNING, TaskStatus.QUEUED):
                node.status = TaskStatus.CANCELLED
        model.status = TaskStatus.CANCELLED
        await self.checkpoint.save(model)
        logger.info("coordinator.cancelled", graph_id=graph_id)

    async def list_active(self) -> list[str]:
        """Return IDs of all currently active graphs."""
        return await self.checkpoint.list_active()

    # ------------------------------------------------------------------
    # Goal decomposition
    # ------------------------------------------------------------------

    async def _decompose_goal(
        self,
        goal: str,
        user_id: str,
        conversation_id: str,
    ) -> TaskGraph:
        """Use Claude to break a goal into parallel task nodes.

        Falls back to a single-node graph if no API key is available.
        """
        agents = self.registry.list_agents()
        if not agents:
            return self._single_node_graph(goal, "default", user_id, conversation_id)

        agent_desc = "\n".join(f"- {a.name}: {a.description}" for a in agents)

        api_key = self._config.get("anthropic_api_key") or os.environ.get(
            "ANTHROPIC_API_KEY", ""
        )

        if not api_key:
            # No API key — route to best-fit agent as a single task
            logger.info("coordinator.decompose.no_api_key")
            best = agents[0].name  # Simple fallback: first agent
            return self._single_node_graph(goal, best, user_id, conversation_id)

        try:
            import anthropic

            client = anthropic.AsyncAnthropic(api_key=api_key)
            response = await client.messages.create(
                model=self._model,
                max_tokens=2048,
                system=DECOMPOSITION_SYSTEM_PROMPT,
                messages=[
                    {
                        "role": "user",
                        "content": (
                            f"## Available Agents\n{agent_desc}\n\n"
                            f"## Goal\n{goal}"
                        ),
                    }
                ],
            )

            raw_text = response.content[0].text.strip()
            # Strip markdown fences if present
            if raw_text.startswith("```"):
                raw_text = raw_text.split("\n", 1)[1]
                if raw_text.endswith("```"):
                    raw_text = raw_text[: raw_text.rfind("```")]
                raw_text = raw_text.strip()

            tasks_data: list[dict[str, Any]] = json.loads(raw_text)

        except Exception as e:
            logger.error("coordinator.decompose.error", error=str(e))
            best = agents[0].name
            return self._single_node_graph(goal, best, user_id, conversation_id)

        # Build the graph from Claude's decomposition
        return self._build_graph(tasks_data, goal, user_id, conversation_id)

    # ------------------------------------------------------------------
    # Graph construction helpers
    # ------------------------------------------------------------------

    def _build_graph(
        self,
        tasks_data: list[dict[str, Any]],
        goal: str,
        user_id: str,
        conversation_id: str,
    ) -> TaskGraph:
        """Convert Claude's JSON task list into a TaskGraph."""
        model = TaskGraphModel(
            name=goal[:80],
            goal=goal,
            user_id=user_id,
            conversation_id=conversation_id,
        )
        graph = TaskGraph(model)

        # First pass: create nodes indexed by name
        name_to_id: dict[str, str] = {}
        for t in tasks_data:
            node = TaskNode(
                name=t.get("name", "task"),
                description=t.get("description", goal),
                assigned_agent=t.get("assigned_agent", "default"),
            )
            graph.add_node(node)
            name_to_id[t.get("name", node.id)] = node.id

        # Second pass: wire dependencies
        for t in tasks_data:
            node_id = name_to_id.get(t.get("name", ""))
            if node_id is None:
                continue
            for dep_name in t.get("dependencies", []):
                dep_id = name_to_id.get(dep_name)
                if dep_id:
                    graph.add_dependency(node_id, dep_id)

        logger.info(
            "coordinator.decompose.success",
            graph_id=model.id,
            node_count=len(model.nodes),
        )
        return graph

    @staticmethod
    def _single_node_graph(
        goal: str,
        agent_name: str,
        user_id: str,
        conversation_id: str,
    ) -> TaskGraph:
        """Create a trivial single-node graph."""
        model = TaskGraphModel(
            name=goal[:80],
            goal=goal,
            user_id=user_id,
            conversation_id=conversation_id,
        )
        node = TaskNode(
            name="main",
            description=goal,
            assigned_agent=agent_name,
        )
        graph = TaskGraph(model)
        graph.add_node(node)
        return graph
