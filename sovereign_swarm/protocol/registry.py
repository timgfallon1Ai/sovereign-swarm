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


def bootstrap_default_registry() -> "AgentRegistry":
    """Build an AgentRegistry populated with all production swarm agents.

    Each agent is imported and instantiated lazily with graceful failure:
    an agent that can't load (missing optional dependency, missing model,
    etc.) is skipped with a warning rather than breaking the whole registry.

    Used by the CLI `sovereign_swarm agents` command and any consumer that
    wants the full default lineup.
    """
    registry = AgentRegistry()

    # (import_path, class_name, kwargs) — kept as strings so ImportErrors
    # from optional deps don't propagate until the entry is actually tried.
    _entries: list[tuple[str, str, dict[str, Any]]] = [
        ("sovereign_swarm.web_agent", "WebAgent", {}),
        ("sovereign_swarm.scientist.agent", "ScientistAgent", {}),
        ("sovereign_swarm.synesthesia.agent", "SynesthesiaAgent", {}),
        ("sovereign_swarm.digital_twin.agent", "DigitalTwinAgent", {}),
        ("sovereign_swarm.medical.agent", "MedicalAgent", {}),
        ("sovereign_swarm.financial_ops.agent", "FinancialOpsAgent", {}),
        ("sovereign_swarm.personal_finance.agent", "PersonalFinanceAgent", {}),
        ("sovereign_swarm.legal.agent", "LegalAgent", {}),
        ("sovereign_swarm.calendar.agent", "CalendarAgent", {}),
        ("sovereign_swarm.content.agent", "ContentAgent", {}),
        ("sovereign_swarm.curation.agent", "CurationAgent", {}),
        ("sovereign_swarm.recruitment.agent", "RecruitmentAgent", {}),
        ("sovereign_swarm.document_intel.agent", "DocumentIntelAgent", {}),
        ("sovereign_swarm.competitive_intel.agent", "CompetitiveIntelAgent", {}),
        # NOTE: sovereign_swarm.audit currently has store.py only, no agent.py.
        # Re-add this entry when AuditAgent is implemented.
        ("sovereign_swarm.monitoring.agent", "MonitoringAgent", {}),
    ]

    import importlib

    for module_path, class_name, kwargs in _entries:
        try:
            module = importlib.import_module(module_path)
            cls = getattr(module, class_name, None)
            if cls is None:
                logger.debug(
                    "registry.bootstrap.class_missing",
                    module=module_path,
                    cls=class_name,
                )
                continue
            agent = cls(**kwargs)
            registry.register(agent)
        except Exception as exc:  # noqa: BLE001
            logger.debug(
                "registry.bootstrap.skipped",
                module=module_path,
                cls=class_name,
                error=f"{type(exc).__name__}: {exc}",
            )

    return registry
