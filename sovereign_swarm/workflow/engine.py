"""Workflow execution engine."""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

import structlog

from sovereign_swarm.workflow.models import (
    ActionType,
    Workflow,
    WorkflowRun,
    WorkflowStep,
)

logger = structlog.get_logger()


class WorkflowEngine:
    """Executes workflow steps sequentially with condition evaluation and error handling."""

    def __init__(self, agent_registry: Any | None = None) -> None:
        self._agent_registry = agent_registry
        self._active_runs: dict[str, WorkflowRun] = {}

    async def run_workflow(self, workflow: Workflow) -> WorkflowRun:
        """Execute a workflow from start to finish."""
        run = WorkflowRun(workflow_id=workflow.id)
        self._active_runs[run.id] = run

        logger.info(
            "workflow.run_started",
            workflow_id=workflow.id,
            workflow_name=workflow.name,
            run_id=run.id,
        )

        try:
            step_map = {step.name: step for step in workflow.steps}
            current_step = workflow.steps[0] if workflow.steps else None

            while current_step is not None:
                step_result = await self._execute_step(current_step)
                run.step_results.append(step_result)

                if step_result["status"] == "success":
                    next_name = current_step.on_success
                else:
                    next_name = current_step.on_failure
                    if not next_name:
                        # No failure handler -- abort workflow
                        run.status = "failed"
                        break

                current_step = step_map.get(next_name) if next_name else None

            if run.status == "running":
                run.status = "completed"

            run.completed_at = datetime.utcnow()
            workflow.last_run = run.completed_at
            workflow.run_count += 1

        except Exception as e:
            logger.error("workflow.run_failed", run_id=run.id, error=str(e))
            run.status = "failed"
            run.completed_at = datetime.utcnow()
            run.step_results.append({"step": "engine", "status": "error", "error": str(e)})

        finally:
            self._active_runs.pop(run.id, None)

        logger.info(
            "workflow.run_completed",
            run_id=run.id,
            status=run.status,
            steps_executed=len(run.step_results),
        )
        return run

    async def _execute_step(self, step: WorkflowStep) -> dict[str, Any]:
        """Execute a single workflow step with timeout."""
        logger.info("workflow.step_start", step=step.name, action=step.action.type.value)

        # Evaluate conditions
        if step.conditions and not self._evaluate_conditions(step.conditions):
            return {"step": step.name, "status": "skipped", "reason": "conditions not met"}

        try:
            result = await asyncio.wait_for(
                self._dispatch_action(step),
                timeout=step.action.timeout_seconds,
            )
            return {"step": step.name, "status": "success", "result": result}

        except asyncio.TimeoutError:
            logger.warning("workflow.step_timeout", step=step.name)
            return {"step": step.name, "status": "timeout"}

        except Exception as e:
            logger.error("workflow.step_error", step=step.name, error=str(e))
            return {"step": step.name, "status": "error", "error": str(e)}

    async def _dispatch_action(self, step: WorkflowStep) -> dict[str, Any]:
        """Dispatch the step action to the appropriate handler."""
        action = step.action

        if action.type == ActionType.RUN_AGENT:
            return await self._run_agent_action(action.config)
        elif action.type == ActionType.SEND_MESSAGE:
            return await self._send_message_action(action.config)
        elif action.type == ActionType.API_CALL:
            return await self._api_call_action(action.config)
        elif action.type == ActionType.FILE_OPERATION:
            return await self._file_operation_action(action.config)
        elif action.type == ActionType.UPDATE_DATABASE:
            return await self._update_database_action(action.config)
        else:
            return {"status": "unsupported_action", "type": action.type.value}

    @staticmethod
    def _evaluate_conditions(conditions: dict[str, Any]) -> bool:
        """Evaluate step conditions. Phase A: simple key-exists checks."""
        # Future: support rich condition expressions
        return bool(conditions.get("always", True))

    async def _run_agent_action(self, config: dict[str, Any]) -> dict[str, Any]:
        """Dispatch a task to another swarm agent."""
        agent_name = config.get("agent", "")
        task = config.get("task", "")
        logger.info("workflow.run_agent", agent=agent_name, task=task)

        if self._agent_registry:
            # Use the registry to find and invoke the agent
            agent = self._agent_registry.get(agent_name)
            if agent:
                from sovereign_swarm.protocol.swarm_agent import SwarmAgentRequest

                resp = await agent.execute(SwarmAgentRequest(task=task, parameters=config))
                return {"agent": agent_name, "output": resp.output, "status": resp.status}

        return {"agent": agent_name, "status": "stub", "message": f"Agent '{agent_name}' not available in registry"}

    @staticmethod
    async def _send_message_action(config: dict[str, Any]) -> dict[str, Any]:
        """Send a message via configured channel."""
        channel = config.get("channel", "log")
        message = config.get("message", "")
        logger.info("workflow.send_message", channel=channel, message=message[:100])
        return {"channel": channel, "sent": True, "message_preview": message[:200]}

    @staticmethod
    async def _api_call_action(config: dict[str, Any]) -> dict[str, Any]:
        """Make an API call (Phase A: stub)."""
        url = config.get("url", "")
        method = config.get("method", "GET")
        logger.info("workflow.api_call", url=url, method=method)
        return {"url": url, "method": method, "status": "stub"}

    @staticmethod
    async def _file_operation_action(config: dict[str, Any]) -> dict[str, Any]:
        """Perform a file operation (Phase A: stub)."""
        operation = config.get("operation", "read")
        path = config.get("path", "")
        logger.info("workflow.file_op", operation=operation, path=path)
        return {"operation": operation, "path": path, "status": "stub"}

    @staticmethod
    async def _update_database_action(config: dict[str, Any]) -> dict[str, Any]:
        """Update database (Phase A: stub)."""
        table = config.get("table", "")
        logger.info("workflow.db_update", table=table)
        return {"table": table, "status": "stub"}

    def get_active_runs(self) -> list[WorkflowRun]:
        """Return currently running workflows."""
        return list(self._active_runs.values())
