"""Bridge between sovereign-swarm learning and sovereign-ai's cognitive profile."""

from __future__ import annotations

import re

import structlog

from sovereign_swarm.learning.fast_learner import FastLearner
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


class LearningBridge:
    """Bridges sovereign-swarm learning with sovereign-ai's CognitiveProfileManager."""

    def __init__(self, fast_learner: FastLearner, patch_store: SkillPatchStore):
        self.fast_learner = fast_learner
        self.store = patch_store

    async def on_correction(
        self,
        original_task: str,
        correction: str,
        agent_name: str,
    ) -> SkillPatch:
        """Handle corrections from the user -- highest-value learning signal."""
        patch = SkillPatch(
            trigger=PatchTrigger(
                agent_name=agent_name,
                task_keywords=self._extract_keywords(original_task),
            ),
            context=f"User corrected response for: {original_task[:200]}",
            instructions=f"User correction: {correction}",
            source="user_correction",
            confidence=0.9,  # High confidence -- user explicitly corrected
        )
        await self.store.store(patch)
        logger.info(
            "learning_bridge.correction_stored",
            agent=agent_name,
            patch_id=patch.id,
        )
        return patch

    @staticmethod
    def _extract_keywords(text: str) -> list[str]:
        """Extract meaningful keywords from text."""
        words = re.findall(r"[a-z]+", text.lower())
        return [w for w in words if len(w) > 2 and w not in _STOP_WORDS][:20]
