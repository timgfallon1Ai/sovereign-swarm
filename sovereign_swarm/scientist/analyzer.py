"""Result analysis engine for experiment outcomes."""

from __future__ import annotations

from typing import Any

import structlog

from sovereign_swarm.scientist.models import ExperimentResult, Hypothesis

logger = structlog.get_logger()


class ResultAnalyzer:
    def __init__(self, config: Any | None = None):
        self.config = config
        self._client: Any | None = None

    async def analyze(
        self, hypothesis: Hypothesis, results: list[ExperimentResult]
    ) -> dict:
        """Analyze experiment results against hypothesis."""
        # Combine all evidence
        all_evidence = "\n\n".join(
            r.raw_output[:1000] for r in results if r.raw_output
        )
        all_citations: list[dict] = []
        for r in results:
            all_citations.extend(r.citations)

        total_confidence = sum(r.confidence for r in results) / max(
            len(results), 1
        )

        # Determine support level
        supported_count = sum(
            1 for r in results if r.supports_hypothesis is True
        )
        refuted_count = sum(
            1 for r in results if r.supports_hypothesis is False
        )

        if supported_count > refuted_count and total_confidence > 0.5:
            verdict = "supported"
        elif refuted_count > supported_count:
            verdict = "refuted"
        else:
            verdict = "inconclusive"

        # Use Claude for deeper analysis if available
        if self._get_client():
            interpretation = await self._llm_analyze(
                hypothesis, results, all_evidence
            )
        else:
            interpretation = self._rule_based_analysis(hypothesis, results)

        return {
            "verdict": verdict,
            "confidence": total_confidence,
            "interpretation": interpretation,
            "citations": all_citations,
            "evidence_count": len(results),
            "supported_count": supported_count,
            "refuted_count": refuted_count,
        }

    def _get_client(self) -> Any | None:
        if self._client is None:
            try:
                import anthropic

                from sovereign_swarm.config import get_settings

                settings = get_settings()
                if settings.anthropic_api_key:
                    self._client = anthropic.AsyncAnthropic(
                        api_key=settings.anthropic_api_key
                    )
            except Exception:
                pass
        return self._client

    async def _llm_analyze(
        self,
        hypothesis: Hypothesis,
        results: list[ExperimentResult],
        evidence: str,
    ) -> str:
        client = self._get_client()
        if not client:
            return self._rule_based_analysis(hypothesis, results)
        try:
            from sovereign_swarm.config import get_settings

            resp = await client.messages.create(
                model=get_settings().slow_model,
                max_tokens=500,
                messages=[
                    {
                        "role": "user",
                        "content": (
                            f"Hypothesis: {hypothesis.statement}\n\n"
                            f"Evidence:\n{evidence[:3000]}\n\n"
                            f"Analyze whether the evidence supports, refutes, "
                            f"or is inconclusive regarding the hypothesis. "
                            f"Be specific about which evidence supports or contradicts."
                        ),
                    }
                ],
            )
            return resp.content[0].text
        except Exception as e:
            logger.error("analyzer.llm_failed", error=str(e))
            return self._rule_based_analysis(hypothesis, results)

    def _rule_based_analysis(
        self, hypothesis: Hypothesis, results: list[ExperimentResult]
    ) -> str:
        parts = [f"Analysis of hypothesis: {hypothesis.statement}"]
        for r in results:
            if r.supports_hypothesis is True:
                status = "supports"
            elif r.supports_hypothesis is False:
                status = "refutes"
            else:
                status = "inconclusive"
            parts.append(
                f"- Experiment result ({status}, confidence: {r.confidence:.0%}): "
                f"{r.interpretation or r.raw_output[:200]}"
            )
        return "\n".join(parts)
