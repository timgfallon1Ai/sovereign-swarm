"""Persistent audit storage backed by aiosqlite."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import aiosqlite

from sovereign_swarm.audit.models import AuditEntry


_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS swarm_audit_log (
    id TEXT PRIMARY KEY,
    timestamp TEXT NOT NULL,
    event_type TEXT NOT NULL,
    agent_name TEXT NOT NULL,
    graph_id TEXT DEFAULT '',
    node_id TEXT DEFAULT '',
    user_id TEXT DEFAULT '',
    action TEXT NOT NULL,
    input_summary TEXT DEFAULT '',
    output_summary TEXT DEFAULT '',
    status TEXT DEFAULT '',
    metadata TEXT DEFAULT '{}'
);
"""

_CREATE_INDEX = """
CREATE INDEX IF NOT EXISTS idx_audit_graph ON swarm_audit_log (graph_id);
CREATE INDEX IF NOT EXISTS idx_audit_agent ON swarm_audit_log (agent_name);
CREATE INDEX IF NOT EXISTS idx_audit_event ON swarm_audit_log (event_type);
"""


class AuditStore:
    """SQLite-backed audit log store."""

    def __init__(self, db_path: str | Path = "data/swarm_audit.db") -> None:
        self._db_path = str(db_path)
        self._db: aiosqlite.Connection | None = None

    async def initialize(self) -> None:
        """Create the database and tables if needed."""
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(self._db_path)
        await self._db.execute(_CREATE_TABLE)
        await self._db.executescript(_CREATE_INDEX)
        await self._db.commit()

    async def store(self, entry: AuditEntry) -> None:
        """Persist an audit entry."""
        if self._db is None:
            await self.initialize()
        assert self._db is not None

        import orjson

        await self._db.execute(
            """
            INSERT INTO swarm_audit_log
                (id, timestamp, event_type, agent_name, graph_id, node_id,
                 user_id, action, input_summary, output_summary, status, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                entry.id,
                entry.timestamp.isoformat(),
                entry.event_type,
                entry.agent_name,
                entry.graph_id,
                entry.node_id,
                entry.user_id,
                entry.action,
                entry.input_summary,
                entry.output_summary,
                entry.status,
                orjson.dumps(entry.metadata).decode(),
            ),
        )
        await self._db.commit()

    async def query(
        self,
        filters: dict[str, Any] | None = None,
        limit: int = 100,
    ) -> list[AuditEntry]:
        """Query audit entries with optional filters."""
        if self._db is None:
            await self.initialize()
        assert self._db is not None

        import orjson

        where_clauses: list[str] = []
        params: list[Any] = []

        if filters:
            for key, value in filters.items():
                if key in (
                    "event_type", "agent_name", "graph_id",
                    "node_id", "user_id", "status",
                ):
                    where_clauses.append(f"{key} = ?")
                    params.append(value)

        sql = "SELECT * FROM swarm_audit_log"
        if where_clauses:
            sql += " WHERE " + " AND ".join(where_clauses)
        sql += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        rows: list[AuditEntry] = []
        async with self._db.execute(sql, params) as cursor:
            async for row in cursor:
                from datetime import datetime

                rows.append(
                    AuditEntry(
                        id=row[0],
                        timestamp=datetime.fromisoformat(row[1]),
                        event_type=row[2],
                        agent_name=row[3],
                        graph_id=row[4],
                        node_id=row[5],
                        user_id=row[6],
                        action=row[7],
                        input_summary=row[8],
                        output_summary=row[9],
                        status=row[10],
                        metadata=orjson.loads(row[11]) if row[11] else {},
                    )
                )
        return rows

    async def close(self) -> None:
        if self._db:
            await self._db.close()
            self._db = None
