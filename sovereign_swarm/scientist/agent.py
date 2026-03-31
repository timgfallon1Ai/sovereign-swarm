"""ScientistAgent -- SciClaw-style autonomous research agent for the swarm."""

from __future__ import annotations

from typing import Any

import structlog

from sovereign_swarm.integration.ingest_bridge import SovereignIngestBridge
from sovereign_swarm.protocol.swarm_agent import (
    SwarmAgent,
    SwarmAgentCard,
    SwarmAgentRequest,
    SwarmAgentResponse,
)

logger = structlog.get_logger()


class ScientistAgent(SwarmAgent):
    """SciClaw-style autonomous research agent."""

    def __init__(
        self,
        ingest_bridge: SovereignIngestBridge | None = None,
        config: Any | None = None,
    ):
        self.ingest = ingest_bridge
        self.config = config
        self._cycle_manager: Any | None = None

    @property
    def card(self) -> SwarmAgentCard:
        return SwarmAgentCard(
            name="scientist",
            description=(
                "Autonomous scientific research agent -- forms hypotheses, "
                "designs experiments, analyzes results, generates reports "
                "with citations from the knowledge base"
            ),
            domains=["research", "analysis", "science", "hypothesis"],
            supported_intents=[
                "research",
                "hypothesis",
                "experiment",
                "analyze",
                "investigate",
            ],
            capabilities=[
                "hypothesize",
                "experiment",
                "analyze",
                "report",
                "research_cycle",
            ],
        )

    async def execute(self, request: SwarmAgentRequest) -> SwarmAgentResponse:
        """Execute a research task."""
        if not self.ingest or not self.ingest.available:
            return SwarmAgentResponse(
                agent_name="scientist",
                status="error",
                error="Knowledge base (sovereign-ingest) not available",
            )

        try:
            manager = self._get_cycle_manager()
            report = await manager.run(request.task)
            markdown = self._get_reporter().to_markdown(report)

            return SwarmAgentResponse(
                agent_name="scientist",
                status="success",
                output=markdown,
                data={
                    "report_id": report.id,
                    "hypotheses_count": len(report.hypotheses),
                    "experiments_count": len(report.experiments),
                    "citations_count": len(report.citations),
                    "supported": sum(
                        1
                        for h in report.hypotheses
                        if h.status.value == "supported"
                    ),
                    "refuted": sum(
                        1
                        for h in report.hypotheses
                        if h.status.value == "refuted"
                    ),
                },
                confidence=sum(h.confidence for h in report.hypotheses)
                / max(len(report.hypotheses), 1),
            )
        except Exception as e:
            logger.error("scientist.execute_failed", error=str(e))
            return SwarmAgentResponse(
                agent_name="scientist",
                status="error",
                error=str(e),
            )

    def _get_cycle_manager(self) -> Any:
        if self._cycle_manager is None:
            from sovereign_swarm.scientist.analyzer import ResultAnalyzer
            from sovereign_swarm.scientist.cycle import ResearchCycleManager
            from sovereign_swarm.scientist.designer import ExperimentDesigner
            from sovereign_swarm.scientist.hypothesis import HypothesisGenerator
            from sovereign_swarm.scientist.reporter import ReportGenerator
            from sovereign_swarm.scientist.runner import ExperimentRunner

            self._cycle_manager = ResearchCycleManager(
                hypothesis_gen=HypothesisGenerator(self.ingest, self.config),
                designer=ExperimentDesigner(self.ingest, self.config),
                runner=ExperimentRunner(self.ingest, self.config),
                analyzer=ResultAnalyzer(self.config),
                reporter=ReportGenerator(self.config),
                ingest_bridge=self.ingest,
            )
        return self._cycle_manager

    def _get_reporter(self) -> Any:
        from sovereign_swarm.scientist.reporter import ReportGenerator

        return ReportGenerator(self.config)
