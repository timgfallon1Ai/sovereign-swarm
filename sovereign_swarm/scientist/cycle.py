"""Research cycle manager -- orchestrates the full hypothesis-experiment loop."""

from __future__ import annotations

from typing import Any

import structlog

from sovereign_swarm.integration.ingest_bridge import SovereignIngestBridge
from sovereign_swarm.scientist.analyzer import ResultAnalyzer
from sovereign_swarm.scientist.designer import ExperimentDesigner
from sovereign_swarm.scientist.hypothesis import HypothesisGenerator
from sovereign_swarm.scientist.models import (
    Hypothesis,
    HypothesisStatus,
    ResearchCycle,
    ResearchCycleStatus,
    ResearchReport,
)
from sovereign_swarm.scientist.reporter import ReportGenerator
from sovereign_swarm.scientist.runner import ExperimentRunner

logger = structlog.get_logger()


class ResearchCycleManager:
    def __init__(
        self,
        hypothesis_gen: HypothesisGenerator,
        designer: ExperimentDesigner,
        runner: ExperimentRunner,
        analyzer: ResultAnalyzer,
        reporter: ReportGenerator,
        ingest_bridge: SovereignIngestBridge | None = None,
    ):
        self.hypothesis_gen = hypothesis_gen
        self.designer = designer
        self.runner = runner
        self.analyzer = analyzer
        self.reporter = reporter
        self.ingest = ingest_bridge

    async def run_program(self, program_path: str) -> ResearchReport:
        """Run a research cycle from a program.md file.

        Karpathy autoresearch pattern: Markdown-driven experiment
        orchestration. The program.md defines hypotheses, experiments,
        success criteria, and iteration rules declaratively.
        """
        from sovereign_swarm.scientist.program import load_program

        spec = load_program(program_path)
        logger.info(
            "scientist.run_program",
            title=spec.title,
            hypotheses=len(spec.hypotheses),
            experiments=len(spec.experiments),
        )

        cycle = ResearchCycle(
            research_question=spec.question,
            max_iterations=spec.max_iterations,
        )

        # Use program-defined hypotheses instead of generating
        cycle.hypotheses = spec.hypotheses

        # Use program-defined experiments instead of designing
        if spec.experiments:
            cycle.experiments = spec.experiments
            # Run each experiment
            for exp in spec.experiments:
                exp_hyp = next(
                    (h for h in spec.hypotheses if h.id == exp.hypothesis_id),
                    None,
                )
                result = await self.runner.run(exp)
                cycle.results.append(result)

                # Analyze if we have a hypothesis to analyze against
                if exp_hyp:
                    hypothesis_results = [
                        r for r in cycle.results
                        if any(
                            e.hypothesis_id == exp_hyp.id and e.id == r.experiment_id
                            for e in cycle.experiments
                        )
                    ]
                    analysis = await self.analyzer.analyze(exp_hyp, hypothesis_results)
                    exp_hyp.status = HypothesisStatus(analysis["verdict"])
                    exp_hyp.confidence = analysis["confidence"]
        else:
            # No experiments defined — fall back to standard cycle
            return await self.run(spec.question, spec.max_iterations)

        cycle.status = ResearchCycleStatus.COMPLETED
        report = await self.reporter.generate(cycle)
        cycle.report = report

        if self.ingest and self.ingest.available:
            markdown = self.reporter.to_markdown(report)
            await self.ingest.inject_document(
                title=report.title,
                content=markdown,
                source="scientist_program",
                metadata={
                    "cycle_id": cycle.id,
                    "program": spec.source_path or "inline",
                    "question": spec.question,
                },
            )

        return report

    async def run(
        self, question: str, max_iterations: int = 3
    ) -> ResearchReport:
        """Run a complete research cycle."""
        cycle = ResearchCycle(
            research_question=question, max_iterations=max_iterations
        )

        for iteration in range(max_iterations):
            cycle.current_iteration = iteration + 1
            logger.info(
                "scientist.iteration",
                iteration=cycle.current_iteration,
                question=question[:80],
            )

            # 1. Generate hypotheses (refine if not first iteration)
            if iteration == 0:
                hypotheses = await self.hypothesis_gen.generate(question)
            else:
                # Refine based on previous results
                inconclusive = [
                    h
                    for h in cycle.hypotheses
                    if h.status == HypothesisStatus.INCONCLUSIVE
                ]
                if not inconclusive:
                    break  # All hypotheses resolved
                hypotheses = await self._refine_hypotheses(
                    inconclusive, cycle.results
                )

            cycle.hypotheses.extend(hypotheses)

            # 2. Design experiments for each hypothesis
            for h in hypotheses:
                h.status = HypothesisStatus.TESTING
                experiments = await self.designer.design(h)
                cycle.experiments.extend(experiments)

                # 3. Run experiments
                for exp in experiments:
                    result = await self.runner.run(exp)
                    cycle.results.append(result)

                # 4. Analyze results for this hypothesis
                # Gather results for experiments belonging to this hypothesis
                hypothesis_results = [
                    r
                    for r in cycle.results
                    if any(
                        e.hypothesis_id == h.id and e.id == r.experiment_id
                        for e in cycle.experiments
                    )
                ]
                analysis = await self.analyzer.analyze(h, hypothesis_results)
                h.status = HypothesisStatus(analysis["verdict"])
                h.confidence = analysis["confidence"]

            # Check if we can stop early
            all_resolved = all(
                h.status != HypothesisStatus.INCONCLUSIVE
                for h in cycle.hypotheses
            )
            if all_resolved:
                break

        # 5. Generate report
        cycle.status = ResearchCycleStatus.COMPLETED
        report = await self.reporter.generate(cycle)
        cycle.report = report

        # 6. Feed back to knowledge base
        if self.ingest and self.ingest.available:
            markdown = self.reporter.to_markdown(report)
            await self.ingest.inject_document(
                title=report.title,
                content=markdown,
                source="scientist",
                metadata={
                    "cycle_id": cycle.id,
                    "question": question,
                },
            )

        return report

    async def _refine_hypotheses(
        self,
        inconclusive: list[Hypothesis],
        results: list[Any],
    ) -> list[Hypothesis]:
        """Refine inconclusive hypotheses based on what we learned."""
        refined = []
        for h in inconclusive:
            refined.append(
                Hypothesis(
                    statement=(
                        f"Refined: {h.statement} "
                        f"(with additional constraints)"
                    ),
                    rationale=(
                        "Previous test was inconclusive. Refining approach."
                    ),
                    parent_hypothesis=h.id,
                    knowledge_graph_entities=h.knowledge_graph_entities,
                )
            )
        return refined
