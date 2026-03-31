"""Trigger management for workflow automation."""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any, Callable, Coroutine

import structlog

from sovereign_swarm.workflow.models import TriggerType, Workflow

logger = structlog.get_logger()

# Optional: croniter for schedule parsing
try:
    from croniter import croniter  # type: ignore[import-untyped]

    _HAS_CRONITER = True
except ImportError:
    _HAS_CRONITER = False


class TriggerManager:
    """Monitors trigger conditions and fires workflows when matched."""

    def __init__(self) -> None:
        self._workflows: dict[str, Workflow] = {}
        self._event_handlers: dict[str, list[str]] = {}  # event_name -> [workflow_id]
        self._schedule_tasks: dict[str, asyncio.Task[None]] = {}
        self._on_fire: Callable[[Workflow], Coroutine[Any, Any, None]] | None = None

    def register_workflow(self, workflow: Workflow) -> None:
        """Register a workflow and set up its trigger."""
        self._workflows[workflow.id] = workflow

        trigger = workflow.trigger
        if trigger.type == TriggerType.EVENT:
            event_name = trigger.config.get("event", "")
            if event_name:
                self._event_handlers.setdefault(event_name, []).append(workflow.id)
                logger.info("trigger.event_registered", event=event_name, workflow=workflow.name)

        elif trigger.type == TriggerType.SCHEDULE:
            cron_expr = trigger.config.get("cron", "")
            if cron_expr and _HAS_CRONITER:
                logger.info("trigger.schedule_registered", cron=cron_expr, workflow=workflow.name)
            elif cron_expr:
                logger.warning("trigger.croniter_missing", workflow=workflow.name)

    def unregister_workflow(self, workflow_id: str) -> None:
        """Remove a workflow from trigger monitoring."""
        workflow = self._workflows.pop(workflow_id, None)
        if not workflow:
            return

        # Clean up event handlers
        for event_name, wf_ids in self._event_handlers.items():
            if workflow_id in wf_ids:
                wf_ids.remove(workflow_id)

        # Cancel schedule task
        task = self._schedule_tasks.pop(workflow_id, None)
        if task and not task.done():
            task.cancel()

    async def fire_event(self, event_name: str, event_data: dict[str, Any] | None = None) -> list[str]:
        """Fire an event and trigger any matching workflows. Returns triggered workflow IDs."""
        triggered: list[str] = []
        workflow_ids = self._event_handlers.get(event_name, [])

        for wf_id in workflow_ids:
            workflow = self._workflows.get(wf_id)
            if workflow and workflow.enabled:
                logger.info("trigger.event_fired", event=event_name, workflow=workflow.name)
                if self._on_fire:
                    await self._on_fire(workflow)
                triggered.append(wf_id)

        return triggered

    def set_fire_callback(
        self, callback: Callable[[Workflow], Coroutine[Any, Any, None]]
    ) -> None:
        """Set the callback invoked when a trigger fires."""
        self._on_fire = callback

    def get_next_schedule_time(self, workflow_id: str) -> datetime | None:
        """Get the next scheduled run time for a workflow."""
        workflow = self._workflows.get(workflow_id)
        if not workflow or workflow.trigger.type != TriggerType.SCHEDULE:
            return None

        cron_expr = workflow.trigger.config.get("cron", "")
        if not cron_expr or not _HAS_CRONITER:
            return None

        cron = croniter(cron_expr, datetime.utcnow())
        return cron.get_next(datetime)

    async def start_schedule_loop(self, check_interval: int = 60) -> None:
        """Start monitoring schedule triggers (runs forever)."""
        logger.info("trigger.schedule_loop_started", interval=check_interval)
        while True:
            now = datetime.utcnow()
            for wf_id, workflow in self._workflows.items():
                if (
                    workflow.enabled
                    and workflow.trigger.type == TriggerType.SCHEDULE
                    and _HAS_CRONITER
                ):
                    cron_expr = workflow.trigger.config.get("cron", "")
                    if cron_expr:
                        cron = croniter(cron_expr, workflow.last_run or datetime(2000, 1, 1))
                        next_run = cron.get_next(datetime)
                        if next_run <= now:
                            logger.info("trigger.schedule_fired", workflow=workflow.name)
                            if self._on_fire:
                                await self._on_fire(workflow)
            await asyncio.sleep(check_interval)

    @property
    def registered_workflows(self) -> list[Workflow]:
        return list(self._workflows.values())
