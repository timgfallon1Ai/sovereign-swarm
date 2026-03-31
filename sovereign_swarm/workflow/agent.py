"""WorkflowAgent -- workflow automation for the Sovereign AI swarm."""

from __future__ import annotations

from typing import Any

import structlog

from sovereign_swarm.protocol.swarm_agent import (
    SwarmAgent,
    SwarmAgentCard,
    SwarmAgentRequest,
    SwarmAgentResponse,
)

logger = structlog.get_logger()


class WorkflowAgent(SwarmAgent):
    """Creates, manages, and executes automated workflows."""

    def __init__(self, config: Any | None = None) -> None:
        self.config = config
        self._engine: Any | None = None
        self._trigger_manager: Any | None = None
        self._workflows: dict[str, Any] = {}

    @property
    def card(self) -> SwarmAgentCard:
        return SwarmAgentCard(
            name="workflow",
            description=(
                "Workflow automation agent -- creates, manages, and executes "
                "multi-step automated workflows with scheduling and event triggers"
            ),
            domains=["workflow", "automation", "trigger", "schedule"],
            supported_intents=[
                "create_workflow",
                "list_workflows",
                "run_workflow",
                "workflow_status",
                "list_templates",
            ],
            capabilities=[
                "create_workflow",
                "list_workflows",
                "run_workflow",
                "workflow_status",
                "list_templates",
            ],
        )

    async def execute(self, request: SwarmAgentRequest) -> SwarmAgentResponse:
        """Route workflow requests to the appropriate handler."""
        task = request.task.lower()

        try:
            if "template" in task and "list" in task:
                result = await self._handle_list_templates()
            elif "create" in task or "new" in task:
                result = await self._handle_create(request)
            elif "run" in task or "execute" in task or "start" in task:
                result = await self._handle_run(request)
            elif "status" in task:
                result = await self._handle_status(request)
            elif "list" in task:
                result = await self._handle_list()
            else:
                result = await self._handle_list()

            return SwarmAgentResponse(
                agent_name="workflow",
                status="success",
                output=result.get("markdown", str(result)),
                data=result,
                confidence=0.85,
            )
        except Exception as e:
            logger.error("workflow.execute_failed", error=str(e))
            return SwarmAgentResponse(
                agent_name="workflow",
                status="error",
                error=str(e),
            )

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------

    async def _handle_list_templates(self) -> dict:
        from sovereign_swarm.workflow.templates import WorkflowTemplates

        templates = WorkflowTemplates.list_templates()
        lines = ["## Workflow Templates\n"]
        for t in templates:
            lines.append(f"- **{t['name']}**: {t['description']} (trigger: {t['trigger']})")
        return {"markdown": "\n".join(lines), "templates": templates}

    async def _handle_create(self, request: SwarmAgentRequest) -> dict:
        template_name = request.parameters.get("template", "")

        if template_name:
            from sovereign_swarm.workflow.templates import WorkflowTemplates

            workflow = WorkflowTemplates.get_template(template_name)
            if not workflow:
                return {"markdown": f"Template '{template_name}' not found."}
        else:
            from sovereign_swarm.workflow.models import (
                TriggerType,
                Workflow,
                WorkflowTrigger,
            )

            workflow = Workflow(
                name=request.parameters.get("name", "unnamed_workflow"),
                description=request.parameters.get("description", ""),
                trigger=WorkflowTrigger(
                    type=TriggerType(request.parameters.get("trigger_type", "manual")),
                    config=request.parameters.get("trigger_config", {}),
                ),
            )

        self._workflows[workflow.id] = workflow

        # Register with trigger manager
        trigger_mgr = self._get_trigger_manager()
        trigger_mgr.register_workflow(workflow)

        return {
            "markdown": f"## Workflow Created\n\n**{workflow.name}** (ID: {workflow.id})\n"
            f"Trigger: {workflow.trigger.type.value}\n"
            f"Steps: {len(workflow.steps)}",
            "workflow_id": workflow.id,
            "workflow": workflow.model_dump(),
        }

    async def _handle_run(self, request: SwarmAgentRequest) -> dict:
        workflow_id = request.parameters.get("workflow_id", "")
        workflow = self._workflows.get(workflow_id)

        if not workflow:
            # Try by name
            name = request.parameters.get("name", workflow_id)
            for wf in self._workflows.values():
                if wf.name == name:
                    workflow = wf
                    break

        if not workflow:
            return {"markdown": f"Workflow not found: {workflow_id}"}

        engine = self._get_engine()
        run = await engine.run_workflow(workflow)

        lines = [
            f"## Workflow Run: {workflow.name}",
            f"**Status**: {run.status}",
            f"**Steps executed**: {len(run.step_results)}",
        ]
        for sr in run.step_results:
            lines.append(f"  - {sr.get('step', '?')}: {sr.get('status', '?')}")

        return {
            "markdown": "\n".join(lines),
            "run": run.model_dump(),
        }

    async def _handle_status(self, request: SwarmAgentRequest) -> dict:
        engine = self._get_engine()
        active = engine.get_active_runs()
        lines = [f"## Active Workflow Runs: {len(active)}\n"]
        for run in active:
            wf = self._workflows.get(run.workflow_id)
            name = wf.name if wf else run.workflow_id
            lines.append(f"- **{name}**: {run.status} ({len(run.step_results)} steps completed)")
        if not active:
            lines.append("No active runs.")
        return {"markdown": "\n".join(lines), "active_runs": len(active)}

    async def _handle_list(self) -> dict:
        lines = [f"## Registered Workflows: {len(self._workflows)}\n"]
        for wf in self._workflows.values():
            lines.append(
                f"- **{wf.name}** (ID: {wf.id}) -- "
                f"trigger: {wf.trigger.type.value}, "
                f"steps: {len(wf.steps)}, "
                f"runs: {wf.run_count}, "
                f"enabled: {wf.enabled}"
            )
        if not self._workflows:
            lines.append("No workflows registered. Use templates or create a new one.")
        return {"markdown": "\n".join(lines), "count": len(self._workflows)}

    # ------------------------------------------------------------------
    # Lazy accessors
    # ------------------------------------------------------------------

    def _get_engine(self):
        if self._engine is None:
            from sovereign_swarm.workflow.engine import WorkflowEngine

            self._engine = WorkflowEngine()
        return self._engine

    def _get_trigger_manager(self):
        if self._trigger_manager is None:
            from sovereign_swarm.workflow.triggers import TriggerManager

            self._trigger_manager = TriggerManager()
        return self._trigger_manager
