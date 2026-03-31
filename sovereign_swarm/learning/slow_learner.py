"""System 2 — Background consolidation of skill patches into modules."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any

import structlog

from sovereign_swarm.learning.models import SkillModule, SkillPatch
from sovereign_swarm.learning.patch_store import SkillPatchStore

logger = structlog.get_logger()

_CONSOLIDATION_PROMPT = """\
You are a learning consolidation engine for an AI agent swarm.

Agent: {agent_name}
Below are {count} skill patches accumulated from task outcomes.

{patches_text}

Synthesize these into:
1. A concise system prompt addition (max 200 words) that captures the key lessons.
2. Training data as a list of instruction/response pairs.

Return a JSON object (no markdown fences):
{{
  "name": "<short module name>",
  "description": "<1-sentence description>",
  "system_prompt_addition": "<200 words max>",
  "training_data": [
    {{"instruction": "...", "response": "...", "text": "..."}},
    ...
  ],
  "quality_score": <0.0-1.0>
}}
"""


class SlowLearner:
    """System 2 — background consolidation of fast-learned patches."""

    def __init__(
        self,
        patch_store: SkillPatchStore,
        ingest_bridge: Any = None,
        config: Any = None,
    ):
        self.store = patch_store
        self.ingest = ingest_bridge
        self.config = config
        self._last_consolidation: datetime | None = None
        self._anthropic = None  # lazy init

    def _get_client(self):
        """Lazy-init Anthropic client."""
        if self._anthropic is None:
            try:
                import anthropic

                self._anthropic = anthropic.AsyncAnthropic()
            except Exception:
                self._anthropic = False
        return self._anthropic if self._anthropic is not False else None

    async def consolidate(self) -> dict[str, Any]:
        """Run full consolidation cycle."""
        since = self._last_consolidation or (datetime.utcnow() - timedelta(days=7))

        # 1. Get all patches since last consolidation
        patches = await self.store.get_all_since(since)
        if len(patches) < 3:
            return {"status": "skipped", "reason": "too few patches", "patch_count": len(patches)}

        # 2. Group by agent_name + keyword similarity
        groups = self._group_patches(patches)

        # 3. For each group with 3+ patches, synthesize into SkillModule
        modules_created = 0
        training_records = 0
        for agent_name, group in groups.items():
            if len(group) < 3:
                continue
            module = await self._synthesize_module(agent_name, group)
            if module:
                await self.store.store_module(module)
                await self.store.supersede([p.id for p in group], module.id)
                modules_created += 1
                training_records += len(module.training_data)

                # Push training data to sovereign-ingest if available
                if self.ingest:
                    for record in module.training_data:
                        try:
                            await self.ingest.inject_document(
                                title=f"Skill Module: {module.name}",
                                content=record.get("text", ""),
                                source="swarm_learning",
                                metadata={
                                    "module_id": module.id,
                                    "agent": agent_name,
                                },
                            )
                        except Exception as exc:
                            logger.warning(
                                "slow_learner.ingest_push_failed",
                                module_id=module.id,
                                error=str(exc),
                            )

        # 4. Prune low-value patches
        pruned = await self.store.prune()

        # 5. Update timestamp
        self._last_consolidation = datetime.utcnow()

        result = {
            "status": "completed",
            "patches_processed": len(patches),
            "modules_created": modules_created,
            "training_records": training_records,
            "patches_pruned": pruned,
        }
        logger.info("slow_learner.consolidation_complete", **result)
        return result

    @staticmethod
    def _group_patches(patches: list[SkillPatch]) -> dict[str, list[SkillPatch]]:
        """Group patches by agent name."""
        groups: dict[str, list[SkillPatch]] = defaultdict(list)
        for p in patches:
            key = p.trigger.agent_name or "general"
            groups[key].append(p)
        return dict(groups)

    async def _synthesize_module(
        self, agent_name: str, patches: list[SkillPatch]
    ) -> SkillModule | None:
        """Synthesize patches into a coherent skill module."""
        client = self._get_client()
        if client:
            return await self._llm_synthesize(client, agent_name, patches)
        return self._rule_based_synthesize(agent_name, patches)

    async def _llm_synthesize(
        self, client: Any, agent_name: str, patches: list[SkillPatch]
    ) -> SkillModule | None:
        model = (
            getattr(self.config, "slow_model", "claude-sonnet-4-6-20250514")
            if self.config
            else "claude-sonnet-4-6-20250514"
        )

        patches_text = ""
        for i, p in enumerate(patches, 1):
            patches_text += (
                f"Patch {i} (source={p.source}, confidence={p.confidence:.0%}, "
                f"success_rate={p.success_rate:.0%}):\n"
                f"  Context: {p.context}\n"
                f"  Instructions: {p.instructions}\n\n"
            )

        prompt = _CONSOLIDATION_PROMPT.format(
            agent_name=agent_name,
            count=len(patches),
            patches_text=patches_text,
        )

        try:
            response = await client.messages.create(
                model=model,
                max_tokens=1024,
                messages=[{"role": "user", "content": prompt}],
            )
            text = response.content[0].text.strip()
            if text.startswith("```"):
                text = re.sub(r"^```\w*\n?", "", text)
                text = re.sub(r"\n?```$", "", text)
            data = json.loads(text)

            return SkillModule(
                name=data.get("name", f"{agent_name}_consolidated"),
                description=data.get("description", "Consolidated skill module"),
                agent_name=agent_name,
                patches_consolidated=[p.id for p in patches],
                system_prompt_addition=data.get("system_prompt_addition", ""),
                training_data=data.get("training_data", []),
                quality_score=data.get("quality_score", 0.5),
            )
        except Exception as exc:
            logger.warning("slow_learner.llm_synthesize_failed", error=str(exc))
            return self._rule_based_synthesize(agent_name, patches)

    @staticmethod
    def _rule_based_synthesize(
        agent_name: str, patches: list[SkillPatch]
    ) -> SkillModule:
        """Fallback: concatenate patch instructions into a module."""
        instructions_parts: list[str] = []
        training_data: list[dict[str, str]] = []

        for p in patches:
            instructions_parts.append(f"- {p.instructions}")
            training_data.append(
                {
                    "instruction": f"When encountering: {p.context}",
                    "response": p.instructions,
                    "text": f"Context: {p.context}\nAction: {p.instructions}",
                }
            )

        prompt_addition = (
            f"Learned behaviors for {agent_name}:\n" + "\n".join(instructions_parts)
        )
        # Trim to ~200 words
        words = prompt_addition.split()
        if len(words) > 200:
            prompt_addition = " ".join(words[:200]) + "..."

        avg_confidence = sum(p.confidence for p in patches) / len(patches)

        return SkillModule(
            name=f"{agent_name}_consolidated",
            description=f"Consolidated {len(patches)} patches for {agent_name}",
            agent_name=agent_name,
            patches_consolidated=[p.id for p in patches],
            system_prompt_addition=prompt_addition,
            training_data=training_data,
            quality_score=min(avg_confidence, 1.0),
        )
