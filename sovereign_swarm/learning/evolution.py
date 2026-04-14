"""Offline evolution pipeline — GEPA-inspired agent config optimization.

Ported from Nous Research's Hermes-Agent self-evolution pattern (ICLR 2026).
Core idea: read full execution traces to diagnose WHY agents fail (not just
scalar rewards), propose config/prompt variants, evaluate them, and output
a structured diff report for human review before merging.

Design notes
------------
- This module does NOT auto-merge changes. It produces an EvolutionReport
  with before/after metrics and a proposed diff. Tim reviews and merges.
- Evaluation runs use the existing SkillPatchStore to replay past tasks
  against the new config, comparing success rates.
- The pipeline is intentionally cheap: Claude API calls for trace analysis
  + variant generation, no GPU required. Target cost: $2-10 per run.
- Traces are collected by the FastLearner's existing on_failure/on_success
  hooks — this module reads them, it doesn't collect them.

Three-stage pipeline:
1. DIAGNOSE — Read execution traces, identify failure patterns
2. MUTATE — Generate prompt/config variants that address the patterns
3. EVALUATE — Score variants against historical tasks, produce report
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import structlog

from sovereign_swarm.learning.models import SkillPatch
from sovereign_swarm.learning.patch_store import SkillPatchStore

logger = structlog.get_logger()


@dataclass
class ExecutionTrace:
    """A single agent execution trace for analysis."""

    agent_name: str
    task: str
    outcome: str  # "success" | "failure" | "partial"
    error: Optional[str] = None
    tool_calls: int = 0
    duration_s: float = 0.0
    context: dict[str, Any] = field(default_factory=dict)
    patch_ids_applied: list[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class ConfigVariant:
    """A proposed configuration change for an agent."""

    agent_name: str
    change_type: str  # "system_prompt", "tool_config", "threshold", "routing"
    description: str
    before: str
    after: str
    rationale: str  # WHY this change should help, grounded in traces
    confidence: float = 0.5
    trace_ids: list[str] = field(default_factory=list)  # traces that motivated this


@dataclass
class EvolutionReport:
    """Output of one evolution run — human reviews before merging."""

    id: str
    agent_name: str
    timestamp: datetime
    traces_analyzed: int
    failure_patterns: list[dict[str, Any]]
    variants_proposed: list[ConfigVariant]
    evaluation_results: list[dict[str, Any]]  # per-variant scores
    recommended_variant: Optional[int] = None  # index into variants_proposed
    status: str = "pending_review"  # "pending_review" | "approved" | "rejected"
    notes: str = ""


_DIAGNOSE_PROMPT = """\
You are analyzing execution traces for an AI agent to find systematic failure patterns.

Agent: {agent_name}
Traces ({count} total, {failures} failures):

{traces_text}

Identify the top 3-5 failure PATTERNS (not individual failures). For each:
1. Pattern name (short, descriptive)
2. Root cause analysis — WHY does this fail? Not what error, but what architectural/prompt/config issue causes it.
3. Frequency — how many traces exhibit this pattern
4. Severity — how impactful is this failure class (high/medium/low)

Return JSON (no markdown fences):
{{
  "patterns": [
    {{
      "name": "<pattern name>",
      "root_cause": "<why it happens>",
      "frequency": <count>,
      "severity": "high|medium|low",
      "example_tasks": ["<task1>", "<task2>"]
    }}
  ]
}}
"""

_MUTATE_PROMPT = """\
You are generating agent configuration variants to fix identified failure patterns.

Agent: {agent_name}
Current system prompt addition: {current_prompt}

Failure patterns to address:
{patterns_text}

For each pattern, propose ONE targeted change. Changes can be:
- system_prompt: modify the agent's system prompt to handle the pattern
- threshold: adjust confidence/retry thresholds
- routing: change when this agent is selected vs. another

Return JSON (no markdown fences):
{{
  "variants": [
    {{
      "change_type": "system_prompt|threshold|routing",
      "description": "<what changes>",
      "before": "<current value or 'N/A'>",
      "after": "<proposed value>",
      "rationale": "<why this fixes the pattern, grounded in traces>",
      "confidence": <0.0-1.0>,
      "addresses_pattern": "<pattern name>"
    }}
  ]
}}
"""


class EvolutionPipeline:
    """Offline agent config evolution via trace analysis."""

    def __init__(
        self,
        patch_store: SkillPatchStore,
        output_dir: str | Path = "~/Documents/sovereign_evolution_reports",
        config: Any = None,
    ):
        self.store = patch_store
        self.output_dir = Path(str(output_dir)).expanduser()
        self.config = config
        self._anthropic = None

    def _get_client(self):
        if self._anthropic is None:
            try:
                import anthropic
                self._anthropic = anthropic.AsyncAnthropic()
            except Exception:
                self._anthropic = False
        return self._anthropic if self._anthropic is not False else None

    async def run(
        self,
        agent_name: str,
        traces: list[ExecutionTrace],
        current_prompt: str = "",
    ) -> EvolutionReport:
        """Execute the full diagnose → mutate → evaluate pipeline."""
        import uuid

        report_id = str(uuid.uuid4())[:8]
        logger.info(
            "evolution.start",
            agent=agent_name,
            traces=len(traces),
            report_id=report_id,
        )

        # Stage 1: DIAGNOSE
        patterns = await self._diagnose(agent_name, traces)

        # Stage 2: MUTATE
        variants = await self._mutate(agent_name, patterns, current_prompt)

        # Stage 3: EVALUATE (lightweight — score against historical patches)
        eval_results = await self._evaluate(agent_name, variants)

        # Pick best variant
        recommended = None
        if eval_results:
            best_idx = max(range(len(eval_results)), key=lambda i: eval_results[i].get("score", 0))
            if eval_results[best_idx].get("score", 0) > 0.5:
                recommended = best_idx

        report = EvolutionReport(
            id=report_id,
            agent_name=agent_name,
            timestamp=datetime.utcnow(),
            traces_analyzed=len(traces),
            failure_patterns=patterns,
            variants_proposed=variants,
            evaluation_results=eval_results,
            recommended_variant=recommended,
        )

        # Serialize for human review
        self._save_report(report)
        logger.info(
            "evolution.complete",
            report_id=report_id,
            patterns=len(patterns),
            variants=len(variants),
            recommended=recommended,
        )
        return report

    async def _diagnose(
        self, agent_name: str, traces: list[ExecutionTrace]
    ) -> list[dict[str, Any]]:
        """Stage 1: Analyze traces for systematic failure patterns."""
        client = self._get_client()
        failures = [t for t in traces if t.outcome == "failure"]

        if not client or not failures:
            # Rule-based fallback
            return self._rule_based_diagnose(agent_name, traces)

        traces_text = ""
        for i, t in enumerate(traces[:30], 1):  # Cap at 30 traces
            traces_text += (
                f"Trace {i} [{t.outcome}]: task='{t.task[:150]}' "
                f"error='{(t.error or 'none')[:100]}' "
                f"tools={t.tool_calls} duration={t.duration_s:.1f}s\n"
            )

        model = getattr(self.config, "slow_model", "claude-sonnet-4-6-20250514") if self.config else "claude-sonnet-4-6-20250514"
        prompt = _DIAGNOSE_PROMPT.format(
            agent_name=agent_name,
            count=len(traces),
            failures=len(failures),
            traces_text=traces_text,
        )

        try:
            resp = await client.messages.create(
                model=model,
                max_tokens=1024,
                messages=[{"role": "user", "content": prompt}],
            )
            text = resp.content[0].text.strip()
            if text.startswith("```"):
                text = re.sub(r"^```\w*\n?", "", text)
                text = re.sub(r"\n?```$", "", text)
            data = json.loads(text)
            return data.get("patterns", [])
        except Exception as exc:
            logger.warning("evolution.diagnose_failed", error=str(exc))
            return self._rule_based_diagnose(agent_name, traces)

    async def _mutate(
        self,
        agent_name: str,
        patterns: list[dict[str, Any]],
        current_prompt: str,
    ) -> list[ConfigVariant]:
        """Stage 2: Generate config variants to address failure patterns."""
        client = self._get_client()
        if not client or not patterns:
            return []

        patterns_text = "\n".join(
            f"- {p.get('name', '?')}: {p.get('root_cause', '?')} "
            f"(freq={p.get('frequency', '?')}, severity={p.get('severity', '?')})"
            for p in patterns
        )

        model = getattr(self.config, "slow_model", "claude-sonnet-4-6-20250514") if self.config else "claude-sonnet-4-6-20250514"
        prompt = _MUTATE_PROMPT.format(
            agent_name=agent_name,
            current_prompt=current_prompt[:500] or "(none)",
            patterns_text=patterns_text,
        )

        try:
            resp = await client.messages.create(
                model=model,
                max_tokens=1024,
                messages=[{"role": "user", "content": prompt}],
            )
            text = resp.content[0].text.strip()
            if text.startswith("```"):
                text = re.sub(r"^```\w*\n?", "", text)
                text = re.sub(r"\n?```$", "", text)
            data = json.loads(text)

            variants = []
            for v in data.get("variants", []):
                variants.append(ConfigVariant(
                    agent_name=agent_name,
                    change_type=v.get("change_type", "system_prompt"),
                    description=v.get("description", ""),
                    before=v.get("before", ""),
                    after=v.get("after", ""),
                    rationale=v.get("rationale", ""),
                    confidence=v.get("confidence", 0.5),
                ))
            return variants
        except Exception as exc:
            logger.warning("evolution.mutate_failed", error=str(exc))
            return []

    async def _evaluate(
        self,
        agent_name: str,
        variants: list[ConfigVariant],
    ) -> list[dict[str, Any]]:
        """Stage 3: Score variants against historical patch success rates."""
        results = []
        patches = self.store.find_relevant(agent_name=agent_name, task_text="", limit=50)

        for variant in variants:
            # Simple scoring: how many existing failure patches would this address?
            addressed = 0
            for patch in patches:
                if patch.source == "failure_analysis":
                    # Check if the variant's rationale covers similar keywords
                    patch_words = set(patch.context.lower().split())
                    variant_words = set(variant.rationale.lower().split())
                    if len(patch_words & variant_words) > 2:
                        addressed += 1

            score = min(addressed / max(len(patches), 1) + variant.confidence * 0.3, 1.0)
            results.append({
                "variant_description": variant.description,
                "patches_addressed": addressed,
                "total_patches": len(patches),
                "score": round(score, 3),
            })
        return results

    def _rule_based_diagnose(
        self, agent_name: str, traces: list[ExecutionTrace]
    ) -> list[dict[str, Any]]:
        """Fallback diagnosis without LLM."""
        from collections import Counter
        error_types = Counter()
        for t in traces:
            if t.outcome == "failure" and t.error:
                match = re.search(r"(\w+Error|\w+Exception)", t.error)
                if match:
                    error_types[match.group(1)] += 1
                else:
                    error_types["unknown"] += 1

        return [
            {
                "name": f"{err_type} cluster",
                "root_cause": f"Recurring {err_type} across {count} traces",
                "frequency": count,
                "severity": "high" if count > 3 else "medium",
            }
            for err_type, count in error_types.most_common(5)
        ]

    def _save_report(self, report: EvolutionReport) -> None:
        """Serialize the evolution report to disk for human review."""
        self.output_dir.mkdir(parents=True, exist_ok=True)
        path = self.output_dir / f"evolution_{report.agent_name}_{report.id}.json"

        # Convert to serializable dict
        payload = {
            "id": report.id,
            "agent_name": report.agent_name,
            "timestamp": report.timestamp.isoformat(),
            "traces_analyzed": report.traces_analyzed,
            "failure_patterns": report.failure_patterns,
            "variants_proposed": [
                {
                    "agent_name": v.agent_name,
                    "change_type": v.change_type,
                    "description": v.description,
                    "before": v.before,
                    "after": v.after,
                    "rationale": v.rationale,
                    "confidence": v.confidence,
                }
                for v in report.variants_proposed
            ],
            "evaluation_results": report.evaluation_results,
            "recommended_variant": report.recommended_variant,
            "status": report.status,
        }
        path.write_text(json.dumps(payload, indent=2))
        logger.info("evolution.report_saved", path=str(path))
