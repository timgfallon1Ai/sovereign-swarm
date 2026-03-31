"""Task scheduler for recurring and one-shot scheduled graph executions."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path

import aiosqlite
import structlog

from sovereign_swarm.runtime.checkpoint import CheckpointManager
from sovereign_swarm.runtime.executor import TaskExecutor
from sovereign_swarm.runtime.graph import TaskGraph
from sovereign_swarm.runtime.models import TaskGraphModel

logger = structlog.get_logger()


class TaskScheduler:
    """Schedule one-shot and recurring graph executions backed by SQLite."""

    def __init__(
        self,
        executor: TaskExecutor,
        checkpoint: CheckpointManager,
        db_path: str | Path = "data/checkpoints.db",
        poll_interval: float = 5.0,
    ) -> None:
        self.executor = executor
        self.checkpoint = checkpoint
        self.db_path = Path(db_path)
        self._poll_interval = poll_interval
        self._db: aiosqlite.Connection | None = None
        self._loop_task: asyncio.Task | None = None
        self._running = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def initialize(self) -> None:
        """Create the scheduled_tasks table and open the DB connection."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(str(self.db_path))
        await self._db.execute("PRAGMA journal_mode=WAL")

        await self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS scheduled_tasks (
                graph_id TEXT PRIMARY KEY,
                graph_json TEXT NOT NULL,
                run_at TEXT,
                interval_seconds INTEGER,
                last_run TEXT,
                enabled INTEGER NOT NULL DEFAULT 1
            )
            """
        )
        await self._db.commit()
        logger.info("scheduler.initialized", db_path=str(self.db_path))

    async def start(self) -> None:
        """Start the background scheduling loop."""
        if self._running:
            return
        self._running = True
        self._loop_task = asyncio.create_task(self._run_loop())
        logger.info("scheduler.started")

    async def stop(self) -> None:
        """Stop the background loop gracefully."""
        self._running = False
        if self._loop_task:
            self._loop_task.cancel()
            try:
                await self._loop_task
            except asyncio.CancelledError:
                pass
            self._loop_task = None
        if self._db:
            await self._db.close()
            self._db = None
        logger.info("scheduler.stopped")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def schedule(
        self,
        graph_model: TaskGraphModel,
        run_at: datetime | None = None,
        interval_seconds: int | None = None,
    ) -> None:
        """Schedule a graph for future execution.

        Parameters
        ----------
        graph_model:
            The task graph to execute.
        run_at:
            When to first run the graph (``None`` = immediately on next tick).
        interval_seconds:
            If set, the graph re-runs every *interval_seconds* after each
            completion.  ``None`` means one-shot.
        """
        if self._db is None:
            raise RuntimeError("TaskScheduler not initialized — call initialize() first")

        graph_json = graph_model.model_dump_json()
        run_at_str = run_at.isoformat() if run_at else None

        await self._db.execute(
            """
            INSERT INTO scheduled_tasks
                (graph_id, graph_json, run_at, interval_seconds, last_run, enabled)
            VALUES (?, ?, ?, ?, NULL, 1)
            ON CONFLICT(graph_id) DO UPDATE SET
                graph_json = excluded.graph_json,
                run_at = excluded.run_at,
                interval_seconds = excluded.interval_seconds,
                enabled = 1
            """,
            (graph_model.id, graph_json, run_at_str, interval_seconds),
        )
        await self._db.commit()
        logger.info(
            "scheduler.scheduled",
            graph_id=graph_model.id,
            run_at=run_at_str,
            interval=interval_seconds,
        )

    async def cancel_schedule(self, graph_id: str) -> None:
        """Disable a scheduled task (does not delete the row)."""
        if self._db is None:
            raise RuntimeError("TaskScheduler not initialized — call initialize() first")

        await self._db.execute(
            "UPDATE scheduled_tasks SET enabled = 0 WHERE graph_id = ?",
            (graph_id,),
        )
        await self._db.commit()
        logger.info("scheduler.cancelled", graph_id=graph_id)

    async def delete_schedule(self, graph_id: str) -> None:
        """Remove a scheduled task entirely."""
        if self._db is None:
            raise RuntimeError("TaskScheduler not initialized — call initialize() first")

        await self._db.execute(
            "DELETE FROM scheduled_tasks WHERE graph_id = ?",
            (graph_id,),
        )
        await self._db.commit()
        logger.info("scheduler.deleted", graph_id=graph_id)

    async def list_schedules(self) -> list[dict]:
        """Return all scheduled tasks."""
        if self._db is None:
            raise RuntimeError("TaskScheduler not initialized — call initialize() first")

        async with self._db.execute(
            "SELECT graph_id, run_at, interval_seconds, last_run, enabled "
            "FROM scheduled_tasks ORDER BY run_at"
        ) as cursor:
            rows = await cursor.fetchall()
            return [
                {
                    "graph_id": r[0],
                    "run_at": r[1],
                    "interval_seconds": r[2],
                    "last_run": r[3],
                    "enabled": bool(r[4]),
                }
                for r in rows
            ]

    # ------------------------------------------------------------------
    # Background loop
    # ------------------------------------------------------------------

    async def _run_loop(self) -> None:
        """Poll for due tasks and execute them."""
        while self._running:
            try:
                await self._tick()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error("scheduler.loop.error", error=str(e))

            await asyncio.sleep(self._poll_interval)

    async def _tick(self) -> None:
        """Single pass: find and execute all due tasks."""
        if self._db is None:
            return

        now = datetime.utcnow()
        now_str = now.isoformat()

        # Fetch enabled tasks that are due
        async with self._db.execute(
            """
            SELECT graph_id, graph_json, run_at, interval_seconds
            FROM scheduled_tasks
            WHERE enabled = 1
              AND (run_at IS NULL OR run_at <= ?)
            """,
            (now_str,),
        ) as cursor:
            rows = await cursor.fetchall()

        for graph_id, graph_json, run_at, interval_seconds in rows:
            logger.info("scheduler.firing", graph_id=graph_id)

            try:
                model = TaskGraphModel.model_validate(json.loads(graph_json))
                graph = TaskGraph(model)
                await self.executor.execute_graph(graph)
            except Exception as e:
                logger.error(
                    "scheduler.execution.error",
                    graph_id=graph_id,
                    error=str(e),
                )

            # Update last_run and schedule next run (or disable if one-shot)
            if interval_seconds:
                next_run = datetime.utcnow()
                # Advance from the original run_at to avoid drift
                if run_at:
                    from datetime import timedelta

                    base = datetime.fromisoformat(run_at)
                    next_run = base + timedelta(seconds=interval_seconds)
                    # If next_run is already past, snap to now + interval
                    if next_run <= now:
                        next_run = now + timedelta(seconds=interval_seconds)

                await self._db.execute(
                    """
                    UPDATE scheduled_tasks
                    SET last_run = ?, run_at = ?
                    WHERE graph_id = ?
                    """,
                    (now_str, next_run.isoformat(), graph_id),
                )
            else:
                # One-shot: disable after execution
                await self._db.execute(
                    """
                    UPDATE scheduled_tasks
                    SET last_run = ?, enabled = 0
                    WHERE graph_id = ?
                    """,
                    (now_str, graph_id),
                )

            await self._db.commit()
