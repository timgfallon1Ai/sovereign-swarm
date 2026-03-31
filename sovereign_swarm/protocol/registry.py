"""Agent registry for discovery and routing."""

from __future__ import annotations

from typing import Any

import structlog

from sovereign_swarm.protocol.swarm_agent import (
    SwarmAgent,
    SwarmAgentCard,
    WrappedSwarmAgent,
)

logger = structlog.get_logger()


class AgentRegistry:
    def __init__(self) -> None:
        self._agents: dict[str, SwarmAgent] = {}

    def register(self, agent: SwarmAgent) -> None:
        self._agents[agent.card.name] = agent
        logger.info("registry.registered", name=agent.card.name)

    def deregister(self, name: str) -> None:
        self._agents.pop(name, None)

    def get_agent(self, name: str) -> SwarmAgent | None:
        return self._agents.get(name)

    def list_agents(self) -> list[SwarmAgentCard]:
        return [a.card for a in self._agents.values()]

    def get_agent_for_task(
        self, task: str, intent: str = "", domain: str = ""
    ) -> SwarmAgent | None:
        for agent in self._agents.values():
            if agent.can_handle(intent, domain):
                return agent
        return None

    def wrap_existing_agent(self, base_agent: Any) -> SwarmAgent:
        wrapped = WrappedSwarmAgent(base_agent)
        self.register(wrapped)
        return wrapped

    def wrap_all_from_router(self, router: Any) -> list[SwarmAgent]:
        wrapped: list[SwarmAgent] = []
        for card in router.list_agents():
            agent = router.get_agent(card.name)
            if agent:
                w = self.wrap_existing_agent(agent)
                wrapped.append(w)
        return wrapped
