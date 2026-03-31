"""DigitalTwinAgent -- Tim's digital twin for the Sovereign AI swarm."""

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


class DigitalTwinAgent(SwarmAgent):
    """Models Tim's decision patterns, handles delegation, manages continuity."""

    def __init__(self, config: Any | None = None) -> None:
        self.config = config
        self._cognitive_model: Any | None = None
        self._delegate: Any | None = None
        self._continuity: Any | None = None

    @property
    def card(self) -> SwarmAgentCard:
        return SwarmAgentCard(
            name="digital_twin",
            description=(
                "Digital twin agent -- models Tim's cognitive patterns, "
                "handles delegated queries when Tim is unavailable, "
                "manages continuity protocol for system autonomy boundaries"
            ),
            domains=["digital_twin", "delegation", "continuity", "cognitive", "legacy"],
            supported_intents=[
                "predict_decision",
                "delegate_query",
                "continuity_status",
                "cognitive_snapshot",
                "update_patterns",
            ],
            capabilities=[
                "predict_decision",
                "delegate_query",
                "continuity_status",
                "cognitive_snapshot",
                "update_patterns",
            ],
        )

    async def execute(self, request: SwarmAgentRequest) -> SwarmAgentResponse:
        """Route digital twin requests to the appropriate handler."""
        task = request.task.lower()

        try:
            if "predict" in task or "decision" in task:
                result = await self._handle_predict(request)
            elif "delegate" in task or "query" in task:
                result = await self._handle_delegate(request)
            elif "continuity" in task or "status" in task:
                result = await self._handle_continuity(request)
            elif "snapshot" in task or "cognitive" in task or "profile" in task:
                result = await self._handle_snapshot()
            elif "update" in task and "pattern" in task:
                result = await self._handle_update_pattern(request)
            elif "activate" in task:
                result = await self._handle_activate_continuity(request)
            elif "deactivate" in task:
                result = await self._handle_deactivate_continuity()
            elif "queue" in task or "escalat" in task:
                result = await self._handle_escalation_queue()
            else:
                result = await self._handle_snapshot()

            return SwarmAgentResponse(
                agent_name="digital_twin",
                status="success",
                output=result.get("markdown", str(result)),
                data=result,
                confidence=result.get("confidence", 0.7),
            )
        except Exception as e:
            logger.error("digital_twin.execute_failed", error=str(e))
            return SwarmAgentResponse(
                agent_name="digital_twin",
                status="error",
                error=str(e),
            )

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------

    async def _handle_predict(self, request: SwarmAgentRequest) -> dict:
        scenario = request.parameters.get("scenario", request.task)
        options = request.parameters.get("options", [])
        domain = request.parameters.get("domain", "")

        if not options:
            return {"markdown": "Provide 'options' (list of choices) and optionally 'domain'."}

        model = self._get_cognitive_model()
        prediction = model.predict_decision(scenario, options, domain=domain)

        lines = [
            f"## Decision Prediction",
            f"**Scenario**: {scenario[:200]}",
            f"**Predicted choice**: {prediction['prediction']}",
            f"**Confidence**: {prediction['confidence']:.0%}",
            f"**Domain**: {prediction['domain']}",
            f"**Reasoning**: {prediction['reasoning']}",
            f"**Patterns consulted**: {prediction['patterns_consulted']}",
        ]

        return {
            "markdown": "\n".join(lines),
            "prediction": prediction,
            "confidence": prediction["confidence"],
        }

    async def _handle_delegate(self, request: SwarmAgentRequest) -> dict:
        from sovereign_swarm.digital_twin.models import DelegateQuery

        query = DelegateQuery(
            query=request.parameters.get("query", request.task),
            requester=request.parameters.get("requester", request.user_id),
            access_level=request.parameters.get("access_level", "viewer"),
            context=request.context,
        )

        delegate = self._get_delegate()
        response = delegate.handle_query(query)

        lines = [
            f"## Delegate Response",
            f"**Confidence**: {response.confidence:.0%}",
            f"\n{response.response}",
            f"\n*{response.disclaimer}*",
        ]

        return {
            "markdown": "\n".join(lines),
            "response": response.model_dump(),
            "confidence": response.confidence,
        }

    async def _handle_continuity(self, request: SwarmAgentRequest) -> dict:
        continuity = self._get_continuity()
        status = continuity.get_status()
        queued = continuity.get_queued_decisions()

        active_str = "ACTIVE" if status["active"] else "INACTIVE"
        lines = [
            f"## Continuity Protocol: {active_str}",
        ]

        if status["active"]:
            lines.append(f"**Activated at**: {status['activated_at']}")
            lines.append(f"**Auto-responses**: {'enabled' if status['auto_responses_enabled'] else 'disabled'}")
            lines.append(f"**Queued decisions**: {status['queued_decisions']}")
            lines.append(f"**Max autonomy**: {status['max_autonomy_level']}")

        lines.append("\n**Boundaries:**")
        for boundary in status["boundaries"]:
            lines.append(f"  - {boundary}")

        if queued:
            lines.append(f"\n**Queued for review ({len(queued)}):**")
            for i, q in enumerate(queued[:10]):
                resolved = "RESOLVED" if q.get("resolved") else "PENDING"
                lines.append(f"  {i}. [{resolved}] {q['query'][:100]} (from: {q.get('requester', '?')})")

        return {
            "markdown": "\n".join(lines),
            "status": status,
            "queued_count": len(queued),
        }

    async def _handle_snapshot(self) -> dict:
        model = self._get_cognitive_model()
        snapshot = model.get_snapshot()

        lines = [
            "## Cognitive Snapshot\n",
            "**Active Projects:**",
        ]
        for proj in snapshot.active_projects:
            lines.append(f"  - {proj}")

        lines.append("\n**Decision Patterns:**")
        for pattern in snapshot.decision_patterns:
            lines.append(
                f"  - **{pattern.domain}** (confidence: {pattern.confidence:.0%}, "
                f"observed: {pattern.frequency}x): {pattern.pattern_description[:100]}"
            )

        lines.append("\n**Risk Tolerance:**")
        for domain, risk in snapshot.risk_tolerance.items():
            bar = "=" * int(risk * 10) + "-" * (10 - int(risk * 10))
            lines.append(f"  - {domain}: [{bar}] {risk:.0%}")

        lines.append("\n**Expertise:**")
        for area in snapshot.expertise_areas:
            lines.append(f"  - {area}")

        return {
            "markdown": "\n".join(lines),
            "snapshot": snapshot.model_dump(),
        }

    async def _handle_update_pattern(self, request: SwarmAgentRequest) -> dict:
        domain = request.parameters.get("domain", "")
        description = request.parameters.get("description", "")
        example = request.parameters.get("example", "")

        if not domain or not description:
            return {"markdown": "Provide 'domain' and 'description' to update a pattern."}

        model = self._get_cognitive_model()
        model.update_pattern(domain, description, example)

        return {
            "markdown": f"## Pattern Updated\n\n**Domain**: {domain}\n**Description**: {description}",
        }

    async def _handle_activate_continuity(self, request: SwarmAgentRequest) -> dict:
        contacts = request.parameters.get("escalation_contacts", [])
        auto_responses = request.parameters.get("auto_responses", True)

        continuity = self._get_continuity()
        protocol = continuity.activate(
            escalation_contacts=contacts, auto_responses=auto_responses
        )

        return {
            "markdown": (
                "## Continuity Protocol Activated\n\n"
                f"Auto-responses: {'enabled' if protocol.auto_responses_enabled else 'disabled'}\n"
                f"Escalation contacts: {len(protocol.escalation_contacts)}\n"
                f"Boundaries: {len(protocol.boundaries)} rules active"
            ),
            "protocol": protocol.model_dump(),
        }

    async def _handle_deactivate_continuity(self) -> dict:
        continuity = self._get_continuity()
        protocol = continuity.deactivate()
        queued = len(protocol.queued_decisions)

        return {
            "markdown": (
                f"## Continuity Protocol Deactivated\n\n"
                f"Queued decisions to review: {queued}"
            ),
            "queued_decisions": queued,
        }

    async def _handle_escalation_queue(self) -> dict:
        delegate = self._get_delegate()
        queue = delegate.get_escalation_queue()

        lines = [f"## Escalation Queue: {len(queue)} items\n"]
        for i, item in enumerate(queue):
            q = item.get("query", {})
            lines.append(
                f"{i}. **{q.get('requester', '?')}** ({q.get('access_level', '?')}): "
                f"{q.get('query', '?')[:100]}"
            )
            lines.append(f"   Reason: {item.get('reason', '?')}")

        if not queue:
            lines.append("No items in escalation queue.")

        return {"markdown": "\n".join(lines), "queue": queue}

    # ------------------------------------------------------------------
    # Lazy accessors
    # ------------------------------------------------------------------

    def _get_cognitive_model(self):
        if self._cognitive_model is None:
            from sovereign_swarm.digital_twin.cognitive_model import CognitiveModel

            self._cognitive_model = CognitiveModel()
        return self._cognitive_model

    def _get_delegate(self):
        if self._delegate is None:
            from sovereign_swarm.digital_twin.delegate import DelegateInterface

            self._delegate = DelegateInterface(
                cognitive_model=self._get_cognitive_model()
            )
        return self._delegate

    def _get_continuity(self):
        if self._continuity is None:
            from sovereign_swarm.digital_twin.continuity import ContinuityManager

            self._continuity = ContinuityManager()
        return self._continuity
