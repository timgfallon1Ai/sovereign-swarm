"""Experiment design based on hypothesis characteristics."""

from __future__ import annotations

from typing import Any

import structlog

from sovereign_swarm.integration.ingest_bridge import SovereignIngestBridge
from sovereign_swarm.scientist.models import Experiment, ExperimentType, Hypothesis

logger = structlog.get_logger()


class ExperimentDesigner:
    def __init__(
        self,
        ingest_bridge: SovereignIngestBridge,
        config: Any | None = None,
    ):
        self.ingest = ingest_bridge
        self.config = config

    async def design(self, hypothesis: Hypothesis) -> list[Experiment]:
        """Design experiments to test a hypothesis."""
        experiments = []

        # Always include a literature review
        experiments.append(
            Experiment(
                hypothesis_id=hypothesis.id,
                experiment_type=ExperimentType.LITERATURE_REVIEW,
                description=f"Literature review for: {hypothesis.statement}",
                methodology=(
                    "1. Search knowledge base for supporting/contradicting evidence\n"
                    "2. Search for related papers\n"
                    "3. Analyze citation patterns"
                ),
                data_sources=["arxiv", "journalclub", "nber", "fed"],
            )
        )

        # If hypothesis is quantitative, add data analysis
        quantitative_keywords = [
            "more",
            "less",
            "increase",
            "decrease",
            "correlat",
            "predict",
            "outperform",
        ]
        if any(
            kw in hypothesis.statement.lower() for kw in quantitative_keywords
        ):
            experiments.append(
                Experiment(
                    hypothesis_id=hypothesis.id,
                    experiment_type=ExperimentType.DATA_ANALYSIS,
                    description=f"Data analysis for: {hypothesis.statement}",
                    methodology=(
                        "1. Query relevant data from knowledge base\n"
                        "2. Extract quantitative claims\n"
                        "3. Compare across sources"
                    ),
                    data_sources=["arxiv", "kalshi", "ssrn"],
                )
            )

        # If hypothesis mentions specific methods/models, add comparison
        entities = hypothesis.knowledge_graph_entities
        if len(entities) >= 2:
            experiments.append(
                Experiment(
                    hypothesis_id=hypothesis.id,
                    experiment_type=ExperimentType.COMPARISON,
                    description=f"Compare: {' vs '.join(entities[:3])}",
                    methodology=(
                        "1. Retrieve documentation on each entity\n"
                        "2. Compare capabilities, performance, limitations\n"
                        "3. Synthesize findings"
                    ),
                    data_sources=["arxiv", "journalclub"],
                )
            )

        return experiments
