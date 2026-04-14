"""StrategicIntelAgent — external-first strategic intelligence.

Orchestrates the 5-phase SENSE → MIRROR → GAP DETECT → RECOMMEND → LEARN
pipeline across 7 strategic frameworks for multi-tenant businesses.
"""

from __future__ import annotations

import json
import re
from typing import Any

import structlog

from sovereign_swarm.protocol.swarm_agent import (
    SwarmAgent,
    SwarmAgentCard,
    SwarmAgentRequest,
    SwarmAgentResponse,
)
from sovereign_swarm.strategic_intel.models import (
    FrameworkResult,
    FrameworkTier,
)

logger = structlog.get_logger()


class StrategicIntelAgent(SwarmAgent):
    """Strategic intelligence agent.

    Runs 7 analysis frameworks against EXTERNAL signals, compares
    to internal business state, detects gaps, and produces weekly
    briefings with corrective recommendations. Learns over time.
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._config = config or {}
        self._sensor = None
        self._mirror = None
        self._gap_detector = None
        self._briefing_gen = None
        self._marketplace = None
        self._fast_learner = None
        self._anthropic = None

    @property
    def card(self) -> SwarmAgentCard:
        return SwarmAgentCard(
            name="strategic_intel",
            description=(
                "Strategic intelligence agent — runs 7 analysis frameworks "
                "against external signals, compares to internal state, detects "
                "gaps, and produces weekly briefings with corrective recommendations."
            ),
            version="0.1.0",
            domains=[
                "strategy", "intelligence", "market", "planning",
                "competitive", "content", "distribution",
            ],
            supported_intents=[
                "weekly_intel_cycle",
                "market_breakdown",
                "problem_priority",
                "offer_creation",
                "competitor_map",
                "content_engine",
                "distribution_plan",
                "scale_system",
                "strategic_briefing",
                "trigger_framework",
            ],
            capabilities=[
                "external_sensing",
                "internal_mirroring",
                "gap_detection",
                "strategic_briefing",
                "learning_loop",
            ],
        )

    async def execute(self, request: SwarmAgentRequest) -> SwarmAgentResponse:
        """Route strategic intel tasks."""
        task = request.task.lower()
        params = request.parameters or request.context or {}

        try:
            if "weekly" in task or "cycle" in task:
                result = await self._run_weekly_cycle(params)
            elif "trigger" in task or "framework" in task:
                result = await self._run_single_framework(params)
            elif "briefing" in task or "brief" in task:
                result = await self._get_latest_briefing(params)
            elif "feedback" in task or "outcome" in task:
                result = await self._record_outcome(params)
            else:
                result = await self._run_weekly_cycle(params)

            return SwarmAgentResponse(
                agent_name=self.card.name,
                status="success",
                output=result.get("markdown", str(result)),
                data=result,
                confidence=result.get("confidence", 0.7),
                tokens_used=result.get("tokens_used", 0),
            )
        except Exception as e:
            logger.error("strategic_intel.execute_failed", error=str(e))
            return SwarmAgentResponse(
                agent_name=self.card.name,
                status="error",
                error=str(e),
            )

    async def _run_weekly_cycle(self, params: dict[str, Any]) -> dict[str, Any]:
        """Full pipeline for a tenant."""
        tenant = params.get("tenant", "atx_mats")
        tier = params.get("tier", "tier_1")

        from sovereign_swarm.marketing.brand import get_brand
        brand = get_brand(tenant)

        # Select frameworks
        from sovereign_swarm.strategic_intel.frameworks import (
            ALL_FRAMEWORKS,
            TIER_1_FRAMEWORKS,
        )
        if tier == "tier_1":
            frameworks = [f() for f in TIER_1_FRAMEWORKS]
        else:
            frameworks = [f() for f in ALL_FRAMEWORKS]

        # Run each framework through the pipeline
        results: list[FrameworkResult] = []
        total_tokens = 0

        for fw in frameworks:
            logger.info("strategic_intel.framework_start", framework=fw.name, tenant=tenant)
            fr = await self._execute_framework(fw, tenant, brand)
            results.append(fr)
            total_tokens += fr.tokens_used
            logger.info(
                "strategic_intel.framework_done",
                framework=fw.name,
                gaps=len(fr.gaps),
                signals=len(fr.external_signals),
            )

        # Generate briefing
        briefing_gen = self._get_briefing_gen()
        briefing = await briefing_gen.generate(tenant, results)

        from sovereign_swarm.strategic_intel.briefing import WeeklyBriefGenerator
        markdown = WeeklyBriefGenerator.render_markdown(briefing)

        return {
            "markdown": markdown,
            "briefing_id": briefing.id,
            "tenant": tenant,
            "frameworks_run": len(results),
            "total_gaps": len(briefing.top_gaps),
            "total_signals": sum(len(fr.external_signals) for fr in results),
            "deltas": len(briefing.deltas_from_prior),
            "recommendations": len(briefing.recommendations),
            "tokens_used": total_tokens,
            "cost_usd": briefing.total_cost_usd,
            "confidence": 0.7,
        }

    async def _run_single_framework(self, params: dict[str, Any]) -> dict[str, Any]:
        """Run a single framework on demand."""
        tenant = params.get("tenant", "atx_mats")
        framework_name = params.get("framework", "market_breakdown")

        from sovereign_swarm.marketing.brand import get_brand
        brand = get_brand(tenant)

        from sovereign_swarm.strategic_intel.frameworks import ALL_FRAMEWORKS
        fw_cls = next(
            (f for f in ALL_FRAMEWORKS if f.name == framework_name),
            None,
        )
        if fw_cls is None:
            return {"error": f"Unknown framework: {framework_name}", "confidence": 0.0}

        fw = fw_cls()
        fr = await self._execute_framework(fw, tenant, brand)

        return {
            "markdown": self._format_framework_result(fr),
            "framework": fr.framework_name,
            "tenant": tenant,
            "gaps": len(fr.gaps),
            "signals": len(fr.external_signals),
            "confidence": 0.7,
        }

    async def _get_latest_briefing(self, params: dict[str, Any]) -> dict[str, Any]:
        """Retrieve the most recent briefing for a tenant."""
        tenant = params.get("tenant", "atx_mats")
        briefing_gen = self._get_briefing_gen()
        prior = briefing_gen._load_prior(tenant)
        if prior is None:
            return {"markdown": "No briefing found. Run a weekly cycle first.", "confidence": 0.0}

        from sovereign_swarm.strategic_intel.briefing import WeeklyBriefGenerator
        markdown = WeeklyBriefGenerator.render_markdown(prior)
        return {"markdown": markdown, "confidence": 0.8}

    async def _record_outcome(self, params: dict[str, Any]) -> dict[str, Any]:
        """Record feedback on a recommendation for the learning loop."""
        gap_id = params.get("gap_id", "")
        acted_on = params.get("acted_on", False)
        feedback = params.get("feedback", "")

        learner = self._get_fast_learner()
        if learner and acted_on:
            await learner.on_success(
                "strategic_intel",
                f"recommendation_acted_on:{gap_id}",
                feedback,
                0.8,
            )
        elif learner and not acted_on:
            await learner.on_failure(
                "strategic_intel",
                f"recommendation_ignored:{gap_id}",
                feedback or "User chose not to act",
            )

        return {
            "markdown": f"Outcome recorded for gap {gap_id}.",
            "acted_on": acted_on,
            "confidence": 1.0,
        }

    async def _execute_framework(
        self, framework: Any, tenant: str, brand: Any
    ) -> FrameworkResult:
        """Execute a single framework through the full pipeline."""
        sensor = self._get_sensor()
        mirror = self._get_mirror()
        gap_detector = self._get_gap_detector()

        # Phase 1: SENSE — external signals only
        queries = framework.get_search_queries(tenant, brand)
        signals = await sensor.search_web(queries)

        # Phase 1b: MARKETPLACE — scan Amazon/Walmart/Google Shopping
        # for product businesses (atx_mats, gli)
        marketplace = self._get_marketplace()
        if marketplace.is_marketplace_tenant(tenant):
            mkt_frameworks = {"market_breakdown", "competitor_map", "problem_priority"}
            if framework.name in mkt_frameworks:
                logger.info(
                    "strategic_intel.marketplace_scan",
                    tenant=tenant,
                    framework=framework.name,
                )
                mkt_signals = await marketplace.scan(tenant)
                signals.extend(mkt_signals)

        # Phase 2: SYNTHESIZE external signals
        synthesis = {}
        tokens_used = 0
        if signals:
            prompt = framework.get_synthesis_prompt(signals, brand)
            synthesis, tokens_used = await self._synthesize(prompt)

        # Phase 3: MIRROR — internal state snapshot
        snapshot = await mirror.snapshot(tenant)

        # Phase 4: GAP DETECT — compare external vs internal
        gaps = await gap_detector.detect_gaps(
            framework.name, signals, snapshot, synthesis
        )

        # Estimate cost (rough)
        cost = tokens_used * 0.000003  # ~$3/1M tokens average

        return FrameworkResult(
            framework_name=framework.name,
            tenant=tenant,
            tier=FrameworkTier(framework.tier),
            external_signals=signals,
            synthesis=synthesis,
            gaps=gaps,
            tokens_used=tokens_used,
            cost_usd=round(cost, 4),
        )

    async def _synthesize(self, prompt: str) -> tuple[dict[str, Any], int]:
        """Run the synthesis prompt via Claude and parse JSON output."""
        client = self._get_anthropic()
        if not client:
            return {}, 0

        try:
            from sovereign_swarm.config import get_settings
            settings = get_settings()
            resp = await client.messages.create(
                model=settings.fast_model,
                max_tokens=2000,
                messages=[{"role": "user", "content": prompt}],
            )
            text = resp.content[0].text.strip()
            tokens = (resp.usage.input_tokens or 0) + (resp.usage.output_tokens or 0)

            # Strip markdown fences
            if text.startswith("```"):
                text = re.sub(r"^```\w*\n?", "", text)
                text = re.sub(r"\n?```$", "", text)

            return json.loads(text), tokens
        except json.JSONDecodeError:
            logger.warning("strategic_intel.synthesis_json_failed")
            return {"raw_text": text}, tokens
        except Exception as exc:
            logger.warning("strategic_intel.synthesis_failed", error=str(exc))
            return {}, 0

    @staticmethod
    def _format_framework_result(fr: FrameworkResult) -> str:
        """Format a single framework result as markdown."""
        lines = [
            f"## {fr.framework_name} — {fr.tenant}",
            f"Signals: {len(fr.external_signals)} | Gaps: {len(fr.gaps)} | Cost: ${fr.cost_usd:.3f}",
            "",
        ]
        for gap in fr.gaps:
            lines.append(
                f"- **[{gap.classification.value.upper()}]** "
                f"(sev {gap.severity:.1f}) {gap.description[:150]}"
            )
            if gap.recommendation:
                lines.append(f"  → {gap.recommendation}")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Lazy initializers
    # ------------------------------------------------------------------

    def _get_sensor(self):
        if self._sensor is None:
            from sovereign_swarm.strategic_intel.sensor import ExternalSensor
            self._sensor = ExternalSensor()
        return self._sensor

    def _get_mirror(self):
        if self._mirror is None:
            from sovereign_swarm.strategic_intel.mirror import InternalMirror
            self._mirror = InternalMirror()
        return self._mirror

    def _get_gap_detector(self):
        if self._gap_detector is None:
            from sovereign_swarm.strategic_intel.gap_detector import GapDetector
            self._gap_detector = GapDetector()
        return self._gap_detector

    def _get_briefing_gen(self):
        if self._briefing_gen is None:
            from sovereign_swarm.strategic_intel.briefing import WeeklyBriefGenerator
            self._briefing_gen = WeeklyBriefGenerator()
        return self._briefing_gen

    def _get_marketplace(self):
        if self._marketplace is None:
            from sovereign_swarm.strategic_intel.marketplace import MarketplaceSensor
            self._marketplace = MarketplaceSensor(config=self._config)
        return self._marketplace

    def _get_fast_learner(self):
        if self._fast_learner is None:
            try:
                from sovereign_swarm.learning.fast_learner import FastLearner
                from sovereign_swarm.learning.patch_store import SkillPatchStore
                store = SkillPatchStore()
                self._fast_learner = FastLearner(patch_store=store)
            except Exception:
                self._fast_learner = False
        return self._fast_learner if self._fast_learner is not False else None

    def _get_anthropic(self):
        if self._anthropic is None:
            try:
                import anthropic
                self._anthropic = anthropic.AsyncAnthropic()
            except Exception:
                self._anthropic = False
        return self._anthropic if self._anthropic is not False else None
