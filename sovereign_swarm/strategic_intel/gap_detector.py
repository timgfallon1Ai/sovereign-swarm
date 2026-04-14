"""GapDetector — compares external signals against internal state.

This is the GAP DETECT phase: takes the external synthesis and internal
snapshot, uses Sonnet to classify each finding as blind_spot, confirmed,
opportunity, or threat. Also provides delta computation between runs.
"""

from __future__ import annotations

import difflib
import json
import structlog
import re
from typing import Any

from sovereign_swarm.strategic_intel.models import (
    ExternalSignal,
    Gap,
    GapClassification,
    InternalSnapshot,
    severity_label,
)

logger = structlog.get_logger()


_GAP_PROMPT = """\
You are a strategic intelligence analyst. Compare EXTERNAL market signals \
against INTERNAL business state and classify each finding.

## External Findings ({framework_name})
{synthesis_text}

## Internal Business State ({tenant})
- Brand: {brand_summary}
- Current assumptions:
{assumptions_text}
- Knowledge base excerpts:
{kb_text}

## Classification Task
For each significant external finding, determine:
1. classification: blind_spot | confirmed | opportunity | threat
2. severity: 0.0-1.0 (how urgently does this need attention?)
3. external_evidence: list of supporting facts from the external data
4. internal_state: what the business currently assumes about this area
5. description: the gap described in one sentence
6. recommendation: one actionable sentence

Return a JSON array (no markdown fences):
[{{
  "classification": "...",
  "severity": 0.X,
  "external_evidence": ["fact1", "fact2"],
  "internal_state": "...",
  "description": "...",
  "recommendation": "..."
}}]

Produce 3-7 gaps. Prioritize blind_spots and threats. \
If external data confirms internal assumptions, include 1-2 "confirmed" \
entries to validate what's working. Be specific and actionable.
"""


class GapDetector:
    """Compares external findings against internal state to detect gaps."""

    def __init__(self) -> None:
        self._anthropic = None

    async def detect_gaps(
        self,
        framework_name: str,
        external_signals: list[ExternalSignal],
        internal_snapshot: InternalSnapshot,
        synthesis: dict[str, Any],
    ) -> list[Gap]:
        """Run gap detection via Sonnet."""
        client = self._get_anthropic()
        if not client:
            return self._rule_based_gaps(framework_name, external_signals, internal_snapshot)

        prompt = self._build_prompt(
            framework_name, external_signals, internal_snapshot, synthesis
        )

        try:
            from sovereign_swarm.config import get_settings
            settings = get_settings()
            resp = await client.messages.create(
                model=settings.slow_model,
                max_tokens=1500,
                messages=[{"role": "user", "content": prompt}],
            )
            text = resp.content[0].text.strip()
            if text.startswith("```"):
                text = re.sub(r"^```\w*\n?", "", text)
                text = re.sub(r"\n?```$", "", text)
            data = json.loads(text)

            gaps = []
            for item in data:
                sev = float(item.get("severity", 0.5))
                gaps.append(Gap(
                    framework=framework_name,
                    classification=GapClassification(item.get("classification", "opportunity")),
                    severity=sev,
                    severity_label=severity_label(sev),
                    external_evidence=item.get("external_evidence", []),
                    internal_state=item.get("internal_state", ""),
                    description=item.get("description", ""),
                    recommendation=item.get("recommendation", ""),
                ))
            return gaps
        except Exception as exc:
            logger.warning("gap_detector.llm_failed", error=str(exc))
            return self._rule_based_gaps(framework_name, external_signals, internal_snapshot)

    def _build_prompt(
        self,
        framework_name: str,
        signals: list[ExternalSignal],
        snapshot: InternalSnapshot,
        synthesis: dict[str, Any],
    ) -> str:
        # Build synthesis text
        synthesis_text = json.dumps(synthesis, indent=2, default=str)[:3000]

        # Build brand summary
        bp = snapshot.brand_profile
        brand_summary = (
            f"{bp.get('display_name', '?')} — {bp.get('one_liner', '?')}"
        )

        # Build assumptions
        assumptions_text = "\n".join(
            f"  - {a}" for a in snapshot.current_assumptions
        ) or "  (none documented)"

        # Build KB excerpts
        kb_text = ""
        for ex in snapshot.kb_excerpts[:5]:
            kb_text += f"  - [{ex.get('source', '?')}] {ex.get('text', '')[:200]}\n"
        kb_text = kb_text or "  (no relevant KB data)"

        return _GAP_PROMPT.format(
            framework_name=framework_name,
            synthesis_text=synthesis_text,
            tenant=snapshot.tenant,
            brand_summary=brand_summary,
            assumptions_text=assumptions_text,
            kb_text=kb_text,
        )

    @staticmethod
    def _rule_based_gaps(
        framework_name: str,
        signals: list[ExternalSignal],
        snapshot: InternalSnapshot,
    ) -> list[Gap]:
        """Fallback gap detection without LLM."""
        gaps = []
        all_facts = []
        for s in signals:
            all_facts.extend(s.extracted_facts)

        assumption_text = " ".join(snapshot.current_assumptions).lower()

        for fact in all_facts[:5]:
            fact_lower = fact.lower()
            # Check if any assumption keywords overlap
            assumption_words = set(assumption_text.split())
            fact_words = set(fact_lower.split())
            overlap = len(assumption_words & fact_words)

            if overlap < 3:
                classification = GapClassification.BLIND_SPOT
                sev = 0.6
            else:
                classification = GapClassification.CONFIRMED
                sev = 0.2

            gaps.append(Gap(
                framework=framework_name,
                classification=classification,
                severity=sev,
                severity_label=severity_label(sev),
                external_evidence=[fact],
                internal_state="(rule-based comparison)",
                description=fact[:200],
                recommendation="Review this finding manually.",
            ))
        return gaps

    @staticmethod
    def compute_delta(
        current_gaps: list[Gap],
        prior_gaps: list[Gap],
    ) -> list[dict[str, Any]]:
        """Diff current gaps vs prior to find new/resolved/escalated."""
        deltas: list[dict[str, Any]] = []
        matched_prior: set[str] = set()

        for curr in current_gaps:
            best_match = None
            best_ratio = 0.0
            for prior in prior_gaps:
                if prior.id in matched_prior:
                    continue
                ratio = difflib.SequenceMatcher(
                    None, curr.description, prior.description
                ).ratio()
                if ratio > best_ratio:
                    best_ratio = ratio
                    best_match = prior

            if best_match and best_ratio >= 0.7:
                matched_prior.add(best_match.id)
                sev_delta = curr.severity - best_match.severity
                if sev_delta >= 0.2:
                    delta_type = "escalated"
                elif sev_delta <= -0.2:
                    delta_type = "de_escalated"
                else:
                    delta_type = "unchanged"
                deltas.append({
                    "type": delta_type,
                    "gap_id": curr.id,
                    "description": curr.description,
                    "severity_change": round(sev_delta, 2),
                    "prior_severity": best_match.severity,
                    "current_severity": curr.severity,
                })
            else:
                deltas.append({
                    "type": "new_gap",
                    "gap_id": curr.id,
                    "description": curr.description,
                    "current_severity": curr.severity,
                })

        # Prior gaps not matched = resolved
        for prior in prior_gaps:
            if prior.id not in matched_prior:
                deltas.append({
                    "type": "resolved",
                    "gap_id": prior.id,
                    "description": prior.description,
                    "prior_severity": prior.severity,
                })

        return deltas

    def _get_anthropic(self):
        if self._anthropic is None:
            try:
                import anthropic
                self._anthropic = anthropic.AsyncAnthropic()
            except Exception:
                self._anthropic = False
        return self._anthropic if self._anthropic is not False else None
