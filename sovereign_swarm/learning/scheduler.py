"""Idle-time consolidation scheduler for the learning system."""

from __future__ import annotations

import asyncio
from datetime import datetime

import structlog

from sovereign_swarm.learning.slow_learner import SlowLearner

logger = structlog.get_logger()


class LearningScheduler:
    """Triggers System 2 consolidation during idle periods."""

    def __init__(self, slow_learner: SlowLearner, idle_threshold: int = 300):
        self.slow_learner = slow_learner
        self.idle_threshold = idle_threshold  # seconds
        self._last_activity = datetime.utcnow()
        self._task: asyncio.Task | None = None
        self._running = False
        self._consolidating = False

    async def start(self) -> None:
        """Start the background scheduler loop."""
        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info(
            "learning_scheduler.started",
            idle_threshold=self.idle_threshold,
        )

    async def stop(self) -> None:
        """Stop the scheduler."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("learning_scheduler.stopped")

    def notify_activity(self) -> None:
        """Called when any task starts or completes to reset idle timer."""
        self._last_activity = datetime.utcnow()

    @property
    def is_consolidating(self) -> bool:
        return self._consolidating

    async def _run_loop(self) -> None:
        """Main loop: check idle time every 30s and trigger consolidation."""
        while self._running:
            try:
                await asyncio.sleep(30)
            except asyncio.CancelledError:
                break

            if self._consolidating:
                continue

            idle_time = (datetime.utcnow() - self._last_activity).total_seconds()
            if idle_time >= self.idle_threshold:
                self._consolidating = True
                try:
                    result = await self.slow_learner.consolidate()
                    logger.info("learning_scheduler.consolidation_complete", **result)
                except Exception as exc:
                    logger.error(
                        "learning_scheduler.consolidation_failed",
                        error=str(exc),
                    )
                finally:
                    self._consolidating = False
