"""Cost tracker -- records and queries API / infrastructure spend."""

from __future__ import annotations

import asyncio
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import structlog

from sovereign_swarm.monitoring.models import CostEntry

logger = structlog.get_logger()


class CostTracker:
    """Tracks API costs across the ecosystem."""

    # Claude pricing per 1M tokens (as of 2026)
    PRICING: dict[str, dict[str, float]] = {
        "claude-opus-4-6": {"input": 15.0, "output": 75.0},
        "claude-sonnet-4-6": {"input": 3.0, "output": 15.0},
        "claude-haiku-4-5": {"input": 0.80, "output": 4.0},
        # Fallback for model IDs with date suffixes
        "claude-opus-4-6-20250514": {"input": 15.0, "output": 75.0},
        "claude-sonnet-4-6-20250514": {"input": 3.0, "output": 15.0},
        "claude-haiku-4-5-20251001": {"input": 0.80, "output": 4.0},
    }

    DEFAULT_PRICING: dict[str, float] = {"input": 3.0, "output": 15.0}

    def __init__(self, db_path: str = "data/monitoring/costs.db") -> None:
        self.db_path = db_path
        self._daily_total: float = 0.0
        self._entries: list[CostEntry] = []
        self._lock = asyncio.Lock()
        self._initialized = False

    async def initialize(self) -> None:
        """Create SQLite table for cost tracking."""
        if self._initialized:
            return
        path = Path(self.db_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(path))
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS costs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                service TEXT NOT NULL,
                agent_name TEXT DEFAULT '',
                tokens_in INTEGER DEFAULT 0,
                tokens_out INTEGER DEFAULT 0,
                cost_usd REAL DEFAULT 0.0,
                model TEXT DEFAULT ''
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_costs_timestamp ON costs(timestamp)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_costs_agent ON costs(agent_name)"
        )
        conn.commit()
        conn.close()
        self._initialized = True
        logger.info("cost_tracker.initialized", db_path=self.db_path)

    def record(
        self,
        service: str,
        agent_name: str = "",
        model: str = "",
        tokens_in: int = 0,
        tokens_out: int = 0,
    ) -> CostEntry:
        """Record a cost entry."""
        pricing = self.PRICING.get(model, self.DEFAULT_PRICING)
        cost = (tokens_in / 1_000_000 * pricing["input"]) + (
            tokens_out / 1_000_000 * pricing["output"]
        )
        entry = CostEntry(
            service=service,
            agent_name=agent_name,
            model=model,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_usd=cost,
        )
        self._entries.append(entry)
        self._daily_total += cost

        # Persist to SQLite (fire-and-forget)
        try:
            self._persist_entry(entry)
        except Exception as e:
            logger.warning("cost_tracker.persist_failed", error=str(e))

        return entry

    def _persist_entry(self, entry: CostEntry) -> None:
        """Write a single entry to SQLite."""
        path = Path(self.db_path)
        if not path.exists():
            return
        conn = sqlite3.connect(str(path))
        conn.execute(
            """
            INSERT INTO costs (timestamp, service, agent_name, tokens_in, tokens_out, cost_usd, model)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                entry.timestamp.isoformat(),
                entry.service,
                entry.agent_name,
                entry.tokens_in,
                entry.tokens_out,
                entry.cost_usd,
                entry.model,
            ),
        )
        conn.commit()
        conn.close()

    async def get_daily_cost(self) -> float:
        """Return today's total spend from in-memory cache."""
        return self._daily_total

    async def get_cost_by_agent(self, days: int = 7) -> dict[str, float]:
        """Cost breakdown by agent over N days."""
        cutoff = datetime.utcnow() - timedelta(days=days)
        breakdown: dict[str, float] = {}
        for entry in self._entries:
            if entry.timestamp >= cutoff and entry.agent_name:
                breakdown[entry.agent_name] = (
                    breakdown.get(entry.agent_name, 0.0) + entry.cost_usd
                )

        # Also query persisted data
        try:
            breakdown = self._merge_db_breakdown(
                breakdown, "agent_name", cutoff
            )
        except Exception:
            pass
        return breakdown

    async def get_cost_by_service(self, days: int = 7) -> dict[str, float]:
        """Cost breakdown by service over N days."""
        cutoff = datetime.utcnow() - timedelta(days=days)
        breakdown: dict[str, float] = {}
        for entry in self._entries:
            if entry.timestamp >= cutoff:
                breakdown[entry.service] = (
                    breakdown.get(entry.service, 0.0) + entry.cost_usd
                )

        try:
            breakdown = self._merge_db_breakdown(breakdown, "service", cutoff)
        except Exception:
            pass
        return breakdown

    def _merge_db_breakdown(
        self,
        in_memory: dict[str, float],
        group_col: str,
        cutoff: datetime,
    ) -> dict[str, float]:
        """Merge in-memory totals with SQLite history."""
        path = Path(self.db_path)
        if not path.exists():
            return in_memory
        conn = sqlite3.connect(str(path))
        rows = conn.execute(
            f"SELECT {group_col}, SUM(cost_usd) FROM costs "
            "WHERE timestamp >= ? GROUP BY " + group_col,
            (cutoff.isoformat(),),
        ).fetchall()
        conn.close()

        merged = dict(in_memory)
        for key, total in rows:
            if key:
                merged[key] = max(merged.get(key, 0.0), total)
        return merged
