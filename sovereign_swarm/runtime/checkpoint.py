"""Checkpoint manager for persisting task graph state via aiosqlite."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import aiosqlite
import structlog

from sovereign_swarm.runtime.models import TaskGraphModel, TaskStatus

logger = structlog.get_logger()

TERMINAL_STATUSES = {TaskStatus.SUCCESS, TaskStatus.FAILED, TaskStatus.CANCELLED}


class CheckpointManager:
    """Persists task graph state to SQLite for crash recovery and history."""

    def __init__(self, db_path: str | Path = "data/checkpoints.db") -> None:
        self.db_path = Path(db_path)
        self._db: aiosqlite.Connection | None = None

    async def initialize(self) -> None:
        """Create tables if they don't exist."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(str(self.db_path))
        await self._db.execute("PRAGMA journal_mode=WAL")

        await self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS checkpoints (
                graph_id TEXT PRIMARY KEY,
                graph_json TEXT NOT NULL,
                status TEXT NOT NULL,
                last_updated TEXT NOT NULL,
                version INTEGER NOT NULL DEFAULT 1
            )
            """
        )

        await self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS completed_graphs (
                graph_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                goal TEXT NOT NULL,
                graph_json TEXT NOT NULL,
                status TEXT NOT NULL,
                user_id TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                completed_at TEXT NOT NULL,
                node_count INTEGER NOT NULL DEFAULT 0,
                success_count INTEGER NOT NULL DEFAULT 0,
                failure_count INTEGER NOT NULL DEFAULT 0
            )
            """
        )

        await self._db.commit()
        logger.info("checkpoint.initialized", db_path=str(self.db_path))

    async def save(self, graph: TaskGraphModel) -> None:
        """Upsert graph to checkpoints. If terminal, also insert into completed_graphs."""
        if self._db is None:
            raise RuntimeError("CheckpointManager not initialized — call initialize() first")

        graph_json = graph.model_dump_json()
        now = datetime.utcnow().isoformat()

        # Upsert into checkpoints
        await self._db.execute(
            """
            INSERT INTO checkpoints (graph_id, graph_json, status, last_updated, version)
            VALUES (?, ?, ?, ?, 1)
            ON CONFLICT(graph_id) DO UPDATE SET
                graph_json = excluded.graph_json,
                status = excluded.status,
                last_updated = excluded.last_updated,
                version = version + 1
            """,
            (graph.id, graph_json, graph.status.value, now),
        )

        # If terminal, archive to completed_graphs
        if graph.status in TERMINAL_STATUSES:
            nodes = graph.nodes.values()
            node_count = len(graph.nodes)
            success_count = sum(1 for n in nodes if n.status == TaskStatus.SUCCESS)
            failure_count = sum(1 for n in nodes if n.status == TaskStatus.FAILED)
            completed_at = (graph.completed_at or datetime.utcnow()).isoformat()

            await self._db.execute(
                """
                INSERT OR REPLACE INTO completed_graphs
                    (graph_id, name, goal, graph_json, status, user_id,
                     created_at, completed_at, node_count, success_count, failure_count)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    graph.id,
                    graph.name,
                    graph.goal,
                    graph_json,
                    graph.status.value,
                    graph.user_id,
                    graph.created_at.isoformat(),
                    completed_at,
                    node_count,
                    success_count,
                    failure_count,
                ),
            )

        await self._db.commit()
        logger.debug(
            "checkpoint.saved",
            graph_id=graph.id,
            status=graph.status.value,
        )

    async def load(self, graph_id: str) -> dict | None:
        """Load graph JSON — try active checkpoints first, then completed_graphs."""
        if self._db is None:
            raise RuntimeError("CheckpointManager not initialized — call initialize() first")

        # Try checkpoints first
        async with self._db.execute(
            "SELECT graph_json FROM checkpoints WHERE graph_id = ?", (graph_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return json.loads(row[0])

        # Fall back to completed_graphs
        async with self._db.execute(
            "SELECT graph_json FROM completed_graphs WHERE graph_id = ?", (graph_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return json.loads(row[0])

        return None

    async def list_active(self) -> list[str]:
        """Return all graph_ids in checkpoints with non-terminal status."""
        if self._db is None:
            raise RuntimeError("CheckpointManager not initialized — call initialize() first")

        terminal_values = tuple(s.value for s in TERMINAL_STATUSES)
        placeholders = ",".join("?" for _ in terminal_values)
        query = f"SELECT graph_id FROM checkpoints WHERE status NOT IN ({placeholders})"

        async with self._db.execute(query, terminal_values) as cursor:
            rows = await cursor.fetchall()
            return [row[0] for row in rows]

    async def delete(self, graph_id: str) -> None:
        """Remove a graph from the active checkpoints table."""
        if self._db is None:
            raise RuntimeError("CheckpointManager not initialized — call initialize() first")

        await self._db.execute(
            "DELETE FROM checkpoints WHERE graph_id = ?", (graph_id,)
        )
        await self._db.commit()
        logger.debug("checkpoint.deleted", graph_id=graph_id)

    async def close(self) -> None:
        """Close the database connection."""
        if self._db:
            await self._db.close()
            self._db = None
