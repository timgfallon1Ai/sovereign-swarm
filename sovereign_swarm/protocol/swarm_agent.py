"""Base agent abstraction for the swarm with learning integration."""

from __future__ import annotations

from abc import ABC, abstractmethod
from types import SimpleNamespace
from typing import Any

import structlog

logger = structlog.get_logger()


class SwarmAgentCard:
    """Agent self-advertisement."""

    def __init__(
        self,
        name: str,
        description: str,
        version: str = "0.1.0",
        domains: list[str] | None = None,
        supported_intents: list[str] | None = None,
        capabilities: list[str] | None = None,
    ) -> None:
        self.name = name
        self.description = description
        self.version = version
        self.domains = domains or []
        self.supported_intents = supported_intents or []
        self.capabilities = capabilities or []
        self.status = "active"


class SwarmAgentRequest:
    def __init__(
        self,
        task: str,
        context: dict[str, Any] | None = None,
        parameters: dict[str, Any] | None = None,
        user_id: str = "",
        conversation_id: str = "",
        skill_patches: list[dict[str, Any]] | None = None,
    ) -> None:
        self.task = task
        self.context = context or {}
        self.parameters = parameters or {}
        self.user_id = user_id
        self.conversation_id = conversation_id
        self.skill_patches = skill_patches or []


class SwarmAgentResponse:
    def __init__(
        self,
        agent_name: str,
        status: str = "success",
        output: str = "",
        data: dict[str, Any] | None = None,
        confidence: float = 0.0,
        tokens_used: int = 0,
        error: str | None = None,
    ) -> None:
        self.agent_name = agent_name
        self.status = status  # "success", "error", "needs_approval"
        self.output = output
        self.data = data or {}
        self.confidence = confidence
        self.tokens_used = tokens_used
        self.error = error


class SwarmAgent(ABC):
    """Base class for all swarm agents with learning integration."""

    _skill_modules: list[dict[str, Any]] = []

    @property
    @abstractmethod
    def card(self) -> SwarmAgentCard:
        ...

    @abstractmethod
    async def execute(self, request: SwarmAgentRequest) -> SwarmAgentResponse:
        ...

    async def execute_with_learning(
        self, request: SwarmAgentRequest
    ) -> SwarmAgentResponse:
        """Execute with skill patches applied as additional context."""
        if request.skill_patches:
            patch_text = self._format_patches(request.skill_patches)
            if patch_text:
                request.context["skill_patches"] = patch_text
        return await self.execute(request)

    def _format_patches(self, patches: list[dict[str, Any]]) -> str:
        if not patches:
            return ""
        lines = ["## Previously Learned (Apply if relevant)"]
        for p in patches:
            lines.append(f"### When: {p.get('context', 'similar situation')}")
            lines.append(p.get("instructions", ""))
            conf = p.get("confidence", 0)
            applied = p.get("times_applied", 0)
            rate = p.get("success_rate", 0)
            lines.append(
                f"(Confidence: {conf:.0%}, Applied {applied} times, Success: {rate:.0%})"
            )
            lines.append("")
        return "\n".join(lines)

    def can_handle(self, intent: str, domain: str) -> bool:
        c = self.card
        if intent in c.supported_intents:
            return True
        if domain in c.domains:
            return True
        return False

    def load_skill_modules(self, modules: list[dict[str, Any]]) -> None:
        self._skill_modules = modules

    @property
    def enhanced_system_prompt(self) -> str:
        base = self._get_base_system_prompt()
        if not self._skill_modules:
            return base
        additions = "\n\n".join(
            m.get("system_prompt_addition", "")
            for m in self._skill_modules
            if m.get("system_prompt_addition")
        )
        if additions:
            return f"{base}\n\n## Learned Knowledge\n{additions}"
        return base

    def _get_base_system_prompt(self) -> str:
        return f"You are the {self.card.name} agent."


class WrappedSwarmAgent(SwarmAgent):
    """Wraps an existing sovereign-ai BaseAgent to work in the swarm."""

    def __init__(self, base_agent: Any) -> None:
        self._base = base_agent
        self._card_cache: SwarmAgentCard | None = None

    @property
    def card(self) -> SwarmAgentCard:
        if self._card_cache is None:
            bc = self._base.card
            self._card_cache = SwarmAgentCard(
                name=bc.name,
                description=bc.description,
                version=bc.version,
                domains=bc.domains,
                supported_intents=bc.supported_intents,
                capabilities=[c.name for c in bc.capabilities],
            )
        return self._card_cache

    async def execute(self, request: SwarmAgentRequest) -> SwarmAgentResponse:
        # Convert swarm request to sovereign-ai AgentRequest format
        base_req = SimpleNamespace(
            task=request.task,
            context=request.context,
            parameters=request.parameters,
            user_id=request.user_id,
            conversation_id=request.conversation_id,
        )
        try:
            result = await self._base.execute(base_req)
            return SwarmAgentResponse(
                agent_name=result.agent_name,
                status=result.status,
                output=result.output,
                data=result.data,
                confidence=result.confidence,
                tokens_used=result.tokens_used,
            )
        except Exception as e:
            return SwarmAgentResponse(
                agent_name=self.card.name,
                status="error",
                error=str(e),
            )
