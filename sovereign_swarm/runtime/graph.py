"""DAG-based task graph for orchestrating multi-agent work."""

from __future__ import annotations

import networkx as nx
import orjson

from sovereign_swarm.runtime.models import TaskGraphModel, TaskNode, TaskStatus


class TaskGraph:
    """Wraps TaskGraphModel with DAG operations."""

    def __init__(self, model: TaskGraphModel) -> None:
        self.model = model

    # --- Construction ---

    def add_node(self, node: TaskNode) -> None:
        """Add a task node to the graph."""
        self.model.nodes[node.id] = node

    def add_dependency(self, node_id: str, depends_on_id: str) -> None:
        """Declare that *node_id* depends on *depends_on_id*."""
        node = self.model.nodes.get(node_id)
        if node is None:
            raise KeyError(f"Node {node_id} not in graph")
        if depends_on_id not in self.model.nodes:
            raise KeyError(f"Dependency {depends_on_id} not in graph")
        if depends_on_id not in node.dependencies:
            node.dependencies.append(depends_on_id)

    # --- Validation ---

    def validate(self) -> bool:
        """Return True if the graph is a valid DAG."""
        g = self._to_nx()
        return nx.is_directed_acyclic_graph(g)

    # --- Queries ---

    def get_ready_nodes(self) -> list[TaskNode]:
        """Return PENDING nodes whose dependencies have all succeeded."""
        ready: list[TaskNode] = []
        for node in self.model.nodes.values():
            if node.status != TaskStatus.PENDING:
                continue
            deps_met = all(
                self.model.nodes[dep_id].status == TaskStatus.SUCCESS
                for dep_id in node.dependencies
                if dep_id in self.model.nodes
            )
            if deps_met:
                ready.append(node)
        return ready

    def is_complete(self) -> bool:
        """True when every node is in a terminal state."""
        terminal = {TaskStatus.SUCCESS, TaskStatus.FAILED, TaskStatus.CANCELLED}
        return all(n.status in terminal for n in self.model.nodes.values())

    def get_status_summary(self) -> dict[str, int]:
        """Return a count of nodes by status."""
        summary: dict[str, int] = {}
        for node in self.model.nodes.values():
            key = node.status.value
            summary[key] = summary.get(key, 0) + 1
        return summary

    # --- Serialization ---

    def to_json(self) -> str:
        """Serialize the graph model to JSON."""
        return self.model.model_dump_json()

    @classmethod
    def from_json(cls, data: str) -> TaskGraph:
        """Deserialize from JSON."""
        model = TaskGraphModel.model_validate(orjson.loads(data))
        return cls(model)

    # --- Internal ---

    def _to_nx(self) -> nx.DiGraph:
        g = nx.DiGraph()
        for nid in self.model.nodes:
            g.add_node(nid)
        for node in self.model.nodes.values():
            for dep_id in node.dependencies:
                g.add_edge(dep_id, node.id)
        return g
