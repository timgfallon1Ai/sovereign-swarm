"""System 1 — Fast, immediate learning from task outcomes."""

from __future__ import annotations

import re
from typing import Any

import structlog

from sovereign_swarm.learning.models import PatchTrigger, SkillPatch
from sovereign_swarm.learning.patch_store import SkillPatchStore

logger = structlog.get_logger()

_STOP_WORDS = frozenset(
    {
        "the", "a", "an", "is", "are", "was", "were", "in", "on", "at", "to",
        "for", "of", "with", "and", "or", "but", "not", "this", "that", "it",
        "my", "your", "we", "they", "he", "she", "be", "do", "have", "has",
        "had", "will", "can", "could", "would", "should", "may", "might",
    }
)

_FAILURE_PROMPT = """\
You are a learning analyst for an AI agent swarm. An agent failed a task.

Agent: {agent_name}
Task: {task}
Error: {error}
Context: {context}

Analyze this failure and produce a JSON object (no markdown fences) with:
{{
  "intent_pattern": "<regex that matches similar task intents, or empty string>",
  "error_pattern": "<regex that matches this class of errors>",
  "task_keywords": ["keyword1", "keyword2", ...],
  "context": "<1-sentence description of when this applies>",
  "instructions": "<2-3 sentences: what the agent should do differently>"
}}

Be specific and actionable. Focus on preventing this exact class of failure.
"""

_SUCCESS_PROMPT = """\
You are a learning analyst for an AI agent swarm. An agent succeeded with high confidence.

Agent: {agent_name}
Task: {task}
Output summary: {output_summary}

Extract the successful approach as a JSON object (no markdown fences):
{{
  "task_keywords": ["keyword1", "keyword2", ...],
  "context": "<1-sentence description of when to use this approach>",
  "instructions": "<2-3 sentences: the approach/strategy that worked>"
}}
"""


def _extract_keywords(text: str) -> list[str]:
    """Extract meaningful keywords from text."""
    words = re.findall(r"[a-z]+", text.lower())
    return [w for w in words if len(w) > 2 and w not in _STOP_WORDS][:20]


def _extract_error_type(error: str) -> str:
    """Extract a simple error pattern from an error message."""
    # Try to get the exception class name
    match = re.search(r"(\w+Error|\w+Exception|\w+Failure)", error)
    if match:
        return re.escape(match.group(1))
    # Fall back to first meaningful phrase
    first_line = error.strip().split("\n")[0][:80]
    return re.escape(first_line)


class FastLearner:
    """System 1 — immediate learning from task outcomes."""

    def __init__(self, patch_store: SkillPatchStore, config: Any = None):
        self.store = patch_store
        self.config = config
        self._anthropic = None  # lazy init

    def _get_client(self):
        """Lazy-init Anthropic client."""
        if self._anthropic is None:
            try:
                import anthropic

                self._anthropic = anthropic.AsyncAnthropic()
            except Exception:
                self._anthropic = False  # sentinel: unavailable
        return self._anthropic if self._anthropic is not False else None

    async def on_failure(
        self,
        agent_name: str,
        task: str,
        error: str,
        context: dict[str, Any] | None = None,
    ) -> SkillPatch | None:
        """Analyze failure and create a reusable skill patch."""
        logger.info(
            "fast_learner.on_failure",
            agent=agent_name,
            task=task[:120],
            error=error[:120],
        )

        client = self._get_client()
        if client:
            patch = await self._llm_failure_analysis(client, agent_name, task, error, context)
        else:
            patch = self._rule_based_failure_patch(agent_name, task, error)

        if patch:
            await self.store.store(patch)
        return patch

    async def on_success(
        self,
        agent_name: str,
        task: str,
        output: str,
        confidence: float,
    ) -> SkillPatch | None:
        """Capture successful approaches for high-confidence results."""
        if confidence < 0.85:
            return None

        logger.info(
            "fast_learner.on_success",
            agent=agent_name,
            task=task[:120],
            confidence=confidence,
        )

        client = self._get_client()
        if client:
            patch = await self._llm_success_capture(client, agent_name, task, output)
        else:
            patch = self._rule_based_success_patch(agent_name, task)

        if patch:
            await self.store.store(patch)
        return patch

    def get_patches_for_task(
        self,
        agent_name: str,
        task: str,
        intent: str = "",
    ) -> list[SkillPatch]:
        """Get relevant patches synchronously (from in-memory cache)."""
        return self.store.find_relevant(agent_name=agent_name, task_text=task, intent=intent)

    @staticmethod
    def format_patches_for_prompt(patches: list[SkillPatch]) -> str:
        """Format patches as markdown for agent prompt injection."""
        if not patches:
            return ""
        lines = ["## Previously Learned (Apply if relevant)"]
        for p in patches:
            lines.append(f"### When: {p.context}")
            lines.append(p.instructions)
            lines.append(
                f"(Confidence: {p.confidence:.0%}, "
                f"Applied {p.times_applied}x, "
                f"Success: {p.success_rate:.0%})"
            )
            lines.append("")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # LLM-based analysis
    # ------------------------------------------------------------------

    async def _llm_failure_analysis(
        self,
        client,
        agent_name: str,
        task: str,
        error: str,
        context: dict[str, Any] | None,
    ) -> SkillPatch | None:
        import json as _json

        model = getattr(self.config, "fast_model", "claude-haiku-4-5-20251001") if self.config else "claude-haiku-4-5-20251001"
        prompt = _FAILURE_PROMPT.format(
            agent_name=agent_name,
            task=task[:500],
            error=error[:500],
            context=_json.dumps(context or {})[:300],
        )
        try:
            response = await client.messages.create(
                model=model,
                max_tokens=512,
                messages=[{"role": "user", "content": prompt}],
            )
            text = response.content[0].text.strip()
            # Strip markdown fences if present
            if text.startswith("```"):
                text = re.sub(r"^```\w*\n?", "", text)
                text = re.sub(r"\n?```$", "", text)
            data = _json.loads(text)

            return SkillPatch(
                trigger=PatchTrigger(
                    agent_name=agent_name,
                    intent_pattern=data.get("intent_pattern", ""),
                    error_pattern=data.get("error_pattern", ""),
                    task_keywords=data.get("task_keywords", _extract_keywords(task)),
                ),
                context=data.get("context", f"Failure during: {task[:200]}"),
                instructions=data.get("instructions", "Review error and retry with caution."),
                source="failure_analysis",
                confidence=0.5,
            )
        except Exception as exc:
            logger.warning("fast_learner.llm_failure_fallback", error=str(exc))
            return self._rule_based_failure_patch(agent_name, task, error)

    async def _llm_success_capture(
        self,
        client,
        agent_name: str,
        task: str,
        output: str,
    ) -> SkillPatch | None:
        import json as _json

        model = getattr(self.config, "fast_model", "claude-haiku-4-5-20251001") if self.config else "claude-haiku-4-5-20251001"
        prompt = _SUCCESS_PROMPT.format(
            agent_name=agent_name,
            task=task[:500],
            output_summary=output[:500],
        )
        try:
            response = await client.messages.create(
                model=model,
                max_tokens=512,
                messages=[{"role": "user", "content": prompt}],
            )
            text = response.content[0].text.strip()
            if text.startswith("```"):
                text = re.sub(r"^```\w*\n?", "", text)
                text = re.sub(r"\n?```$", "", text)
            data = _json.loads(text)

            return SkillPatch(
                trigger=PatchTrigger(
                    agent_name=agent_name,
                    task_keywords=data.get("task_keywords", _extract_keywords(task)),
                ),
                context=data.get("context", f"Successful approach for: {task[:200]}"),
                instructions=data.get("instructions", "Apply the same approach as before."),
                source="success_capture",
                confidence=0.7,
            )
        except Exception as exc:
            logger.warning("fast_learner.llm_success_fallback", error=str(exc))
            return self._rule_based_success_patch(agent_name, task)

    # ------------------------------------------------------------------
    # Rule-based fallbacks (no API key)
    # ------------------------------------------------------------------

    @staticmethod
    def _rule_based_failure_patch(
        agent_name: str, task: str, error: str
    ) -> SkillPatch:
        error_pat = _extract_error_type(error)
        keywords = _extract_keywords(task)
        first_line = error.strip().split("\n")[0][:200]

        return SkillPatch(
            trigger=PatchTrigger(
                agent_name=agent_name,
                error_pattern=error_pat,
                task_keywords=keywords,
            ),
            context=f"Agent '{agent_name}' failed with: {first_line}",
            instructions=(
                f"Previously encountered error matching '{error_pat}'. "
                "Check preconditions before attempting this class of task. "
                "Consider breaking the task into smaller steps or validating inputs first."
            ),
            source="failure_analysis",
            confidence=0.4,
        )

    @staticmethod
    def _rule_based_success_patch(agent_name: str, task: str) -> SkillPatch:
        keywords = _extract_keywords(task)
        return SkillPatch(
            trigger=PatchTrigger(
                agent_name=agent_name,
                task_keywords=keywords,
            ),
            context=f"Successful task pattern for '{agent_name}': {task[:200]}",
            instructions=(
                "This type of task has been completed successfully before. "
                "Follow the same general approach and validate outputs."
            ),
            source="success_capture",
            confidence=0.6,
        )
