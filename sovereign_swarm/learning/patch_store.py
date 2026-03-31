"""SQLite-backed skill patch store with in-memory cache."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import aiosqlite
import structlog

from sovereign_swarm.learning.models import PatchTrigger, SkillModule, SkillPatch

logger = structlog.get_logger()

_CREATE_PATCHES = """
CREATE TABLE IF NOT EXISTS skill_patches (
    id TEXT PRIMARY KEY,
    trigger_json TEXT NOT NULL,
    context TEXT NOT NULL,
    instructions TEXT NOT NULL,
    source TEXT NOT NULL,
    confidence REAL NOT NULL DEFAULT 0.5,
    times_applied INTEGER NOT NULL DEFAULT 0,
    times_succeeded INTEGER NOT NULL DEFAULT 0,
    success_rate REAL NOT NULL DEFAULT 0.0,
    created_at TEXT NOT NULL,
    last_applied TEXT,
    superseded_by TEXT,
    tags_json TEXT NOT NULL DEFAULT '[]'
);
"""

_CREATE_MODULES = """
CREATE TABLE IF NOT EXISTS skill_modules (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT NOT NULL,
    agent_name TEXT NOT NULL,
    patches_consolidated_json TEXT NOT NULL DEFAULT '[]',
    system_prompt_addition TEXT NOT NULL DEFAULT '',
    training_data_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    quality_score REAL NOT NULL DEFAULT 0.0
);
"""


class SkillPatchStore:
    """SQLite + in-memory cache for skill patches and modules."""

    def __init__(self, db_path: str | Path = "data/skill_patches.db"):
        self.db_path = Path(db_path)
        self._cache: dict[str, SkillPatch] = {}
        self._db: aiosqlite.Connection | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def initialize(self) -> None:
        """Create tables and load active patches into memory."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(str(self.db_path))
        await self._db.execute(_CREATE_PATCHES)
        await self._db.execute(_CREATE_MODULES)
        await self._db.commit()

        # Load all active patches into cache
        async with self._db.execute("SELECT * FROM skill_patches") as cursor:
            rows = await cursor.fetchall()
            cols = [d[0] for d in cursor.description]
            for row in rows:
                rec = dict(zip(cols, row))
                patch = self._row_to_patch(rec)
                self._cache[patch.id] = patch

        logger.info("patch_store.initialized", patches_loaded=len(self._cache))

    async def close(self) -> None:
        if self._db:
            await self._db.close()
            self._db = None

    # ------------------------------------------------------------------
    # Patches
    # ------------------------------------------------------------------

    async def store(self, patch: SkillPatch) -> None:
        """INSERT a patch into SQLite and add to cache."""
        assert self._db is not None, "Store not initialized"
        await self._db.execute(
            """INSERT INTO skill_patches
               (id, trigger_json, context, instructions, source, confidence,
                times_applied, times_succeeded, success_rate, created_at,
                last_applied, superseded_by, tags_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                patch.id,
                patch.trigger.model_dump_json(),
                patch.context,
                patch.instructions,
                patch.source,
                patch.confidence,
                patch.times_applied,
                patch.times_succeeded,
                patch.success_rate,
                patch.created_at.isoformat(),
                patch.last_applied.isoformat() if patch.last_applied else None,
                patch.superseded_by,
                json.dumps(patch.tags),
            ),
        )
        await self._db.commit()
        self._cache[patch.id] = patch
        logger.info("patch_store.stored", patch_id=patch.id, source=patch.source)

    def find_relevant(
        self,
        agent_name: str,
        task_text: str,
        intent: str = "",
        error: str = "",
        limit: int = 5,
    ) -> list[SkillPatch]:
        """Search in-memory cache for relevant patches (synchronous)."""
        import re

        task_words = set(task_text.lower().split())
        scored: list[tuple[float, SkillPatch]] = []

        for patch in self._cache.values():
            # Skip superseded or low-confidence patches
            if patch.superseded_by is not None:
                continue
            if patch.confidence < 0.3:
                continue

            # Agent filter
            if patch.trigger.agent_name and agent_name and patch.trigger.agent_name != agent_name:
                continue

            score = 0.0

            # Keyword overlap scoring
            kw_set = set(patch.trigger.task_keywords)
            if kw_set:
                overlap = len(task_words & kw_set)
                score += overlap / max(len(kw_set), 1)

            # Intent pattern matching
            if intent and patch.trigger.intent_pattern:
                try:
                    if re.search(patch.trigger.intent_pattern, intent, re.IGNORECASE):
                        score += 1.0
                except re.error:
                    pass

            # Error pattern matching
            if error and patch.trigger.error_pattern:
                try:
                    if re.search(patch.trigger.error_pattern, error, re.IGNORECASE):
                        score += 2.0  # error matches are high value
                except re.error:
                    pass

            # Boost by confidence and success rate
            score *= (0.5 + patch.confidence)

            if score > 0:
                scored.append((score, patch))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [p for _, p in scored[:limit]]

    async def record_application(self, patch_id: str, succeeded: bool) -> None:
        """Update application stats for a patch."""
        assert self._db is not None
        patch = self._cache.get(patch_id)
        if not patch:
            return

        patch.times_applied += 1
        if succeeded:
            patch.times_succeeded += 1
        patch.success_rate = (
            patch.times_succeeded / patch.times_applied if patch.times_applied > 0 else 0.0
        )
        patch.last_applied = datetime.utcnow()

        await self._db.execute(
            """UPDATE skill_patches
               SET times_applied = ?, times_succeeded = ?, success_rate = ?, last_applied = ?
               WHERE id = ?""",
            (
                patch.times_applied,
                patch.times_succeeded,
                patch.success_rate,
                patch.last_applied.isoformat(),
                patch_id,
            ),
        )
        await self._db.commit()

    async def get_all_since(self, since: datetime) -> list[SkillPatch]:
        """Return patches created since a given datetime (for consolidation)."""
        cutoff = since.isoformat()
        return [
            p
            for p in self._cache.values()
            if p.created_at.isoformat() >= cutoff and p.superseded_by is None
        ]

    async def prune(self, min_success_rate: float = 0.1, min_applications: int = 3) -> int:
        """Delete patches with enough trials but poor outcomes."""
        assert self._db is not None
        to_remove: list[str] = []
        for patch in self._cache.values():
            if patch.superseded_by is not None:
                continue
            if patch.times_applied >= min_applications and patch.success_rate < min_success_rate:
                to_remove.append(patch.id)

        for pid in to_remove:
            await self._db.execute("DELETE FROM skill_patches WHERE id = ?", (pid,))
            self._cache.pop(pid, None)

        if to_remove:
            await self._db.commit()
            logger.info("patch_store.pruned", count=len(to_remove))

        return len(to_remove)

    async def supersede(self, old_ids: list[str], new_id: str) -> None:
        """Mark old patches as superseded by a new module/patch."""
        assert self._db is not None
        for oid in old_ids:
            await self._db.execute(
                "UPDATE skill_patches SET superseded_by = ? WHERE id = ?",
                (new_id, oid),
            )
            if oid in self._cache:
                self._cache[oid].superseded_by = new_id
        await self._db.commit()

    # ------------------------------------------------------------------
    # Modules
    # ------------------------------------------------------------------

    async def store_module(self, module: SkillModule) -> None:
        """Save a consolidated skill module."""
        assert self._db is not None
        await self._db.execute(
            """INSERT INTO skill_modules
               (id, name, description, agent_name, patches_consolidated_json,
                system_prompt_addition, training_data_json, created_at, quality_score)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                module.id,
                module.name,
                module.description,
                module.agent_name,
                json.dumps(module.patches_consolidated),
                module.system_prompt_addition,
                json.dumps(module.training_data),
                module.created_at.isoformat(),
                module.quality_score,
            ),
        )
        await self._db.commit()
        logger.info("patch_store.module_stored", module_id=module.id, name=module.name)

    async def get_modules_for_agent(self, agent_name: str) -> list[SkillModule]:
        """Return all skill modules for a given agent."""
        assert self._db is not None
        async with self._db.execute(
            "SELECT * FROM skill_modules WHERE agent_name = ?", (agent_name,)
        ) as cursor:
            rows = await cursor.fetchall()
            cols = [d[0] for d in cursor.description]
            return [self._row_to_module(dict(zip(cols, row))) for row in rows]

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    async def get_stats(self) -> dict:
        """Return summary statistics."""
        total = len(self._cache)
        active = sum(1 for p in self._cache.values() if p.superseded_by is None)
        superseded = total - active
        success_rates = [
            p.success_rate for p in self._cache.values() if p.times_applied > 0
        ]
        avg_success = sum(success_rates) / len(success_rates) if success_rates else 0.0

        module_count = 0
        if self._db:
            async with self._db.execute("SELECT COUNT(*) FROM skill_modules") as cursor:
                row = await cursor.fetchone()
                module_count = row[0] if row else 0

        return {
            "total_patches": total,
            "active_patches": active,
            "superseded_patches": superseded,
            "modules": module_count,
            "avg_success_rate": round(avg_success, 3),
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_patch(rec: dict) -> SkillPatch:
        trigger = PatchTrigger.model_validate_json(rec["trigger_json"])
        return SkillPatch(
            id=rec["id"],
            trigger=trigger,
            context=rec["context"],
            instructions=rec["instructions"],
            source=rec["source"],
            confidence=rec["confidence"],
            times_applied=rec["times_applied"],
            times_succeeded=rec["times_succeeded"],
            success_rate=rec["success_rate"],
            created_at=datetime.fromisoformat(rec["created_at"]),
            last_applied=(
                datetime.fromisoformat(rec["last_applied"]) if rec["last_applied"] else None
            ),
            superseded_by=rec["superseded_by"],
            tags=json.loads(rec["tags_json"]),
        )

    @staticmethod
    def _row_to_module(rec: dict) -> SkillModule:
        return SkillModule(
            id=rec["id"],
            name=rec["name"],
            description=rec["description"],
            agent_name=rec["agent_name"],
            patches_consolidated=json.loads(rec["patches_consolidated_json"]),
            system_prompt_addition=rec["system_prompt_addition"],
            training_data=json.loads(rec["training_data_json"]),
            created_at=datetime.fromisoformat(rec["created_at"]),
            quality_score=rec["quality_score"],
        )
