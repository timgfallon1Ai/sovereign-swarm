"""SQLite-backed persistence for the support module.

Follows the same aiosqlite pattern as sales_ops/store.py.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import aiosqlite
import structlog

from sovereign_swarm.support.models import (
    Case,
    CaseMessage,
    CaseMessageDirection,
    CasePriority,
    CaseSource,
    CaseStatus,
)

logger = structlog.get_logger()


_SCHEMA = """
CREATE TABLE IF NOT EXISTS cases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant TEXT NOT NULL,
    contact_id INTEGER,
    subject TEXT NOT NULL,
    status TEXT DEFAULT 'new',
    priority TEXT DEFAULT 'normal',
    source TEXT DEFAULT 'email_inbound',
    assigned_to TEXT DEFAULT '',
    tags TEXT DEFAULT '[]',
    metadata TEXT DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    resolved_at TEXT
);

CREATE TABLE IF NOT EXISTS case_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id INTEGER NOT NULL REFERENCES cases(id),
    tenant TEXT NOT NULL,
    direction TEXT NOT NULL,
    sender TEXT DEFAULT '',
    recipient TEXT DEFAULT '',
    subject TEXT DEFAULT '',
    body TEXT DEFAULT '',
    channel TEXT DEFAULT 'email',
    metadata TEXT DEFAULT '{}',
    occurred_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_cases_tenant_status ON cases(tenant, status);
CREATE INDEX IF NOT EXISTS idx_cases_contact ON cases(contact_id);
CREATE INDEX IF NOT EXISTS idx_case_messages_case ON case_messages(case_id);
"""


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


def _parse_iso(val: Any) -> datetime | None:
    if not val:
        return None
    if isinstance(val, datetime):
        return val
    try:
        return datetime.fromisoformat(str(val))
    except (ValueError, TypeError):
        return None


class SupportStore:
    """SQLite persistence for cases + case messages."""

    def __init__(self, db_path: str | Path = "data/support.db") -> None:
        self.db_path = Path(db_path)
        self._db: aiosqlite.Connection | None = None

    async def initialize(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(str(self.db_path))
        await self._db.executescript(_SCHEMA)
        await self._db.commit()
        logger.info("support.store.initialized", db_path=str(self.db_path))

    async def close(self) -> None:
        if self._db is not None:
            await self._db.close()
            self._db = None

    async def _conn(self) -> aiosqlite.Connection:
        if self._db is None:
            await self.initialize()
        assert self._db is not None
        return self._db

    # ------------------------------------------------------------------
    # Cases
    # ------------------------------------------------------------------

    async def create_case(self, case: Case) -> int:
        db = await self._conn()
        cur = await db.execute(
            """INSERT INTO cases (tenant, contact_id, subject, status, priority,
               source, assigned_to, tags, metadata, created_at, updated_at, resolved_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                case.tenant, case.contact_id, case.subject,
                case.status.value, case.priority.value, case.source.value,
                case.assigned_to, json.dumps(case.tags), json.dumps(case.metadata, default=str),
                _iso(case.created_at), _iso(case.updated_at), _iso(case.resolved_at),
            ),
        )
        await db.commit()
        case_id = cur.lastrowid or 0
        logger.info(
            "support.case_created",
            case_id=case_id,
            tenant=case.tenant,
            source=case.source.value,
            subject=case.subject[:80],
        )
        return case_id

    async def update_case(self, case: Case) -> None:
        db = await self._conn()
        case.updated_at = datetime.utcnow()
        await db.execute(
            """UPDATE cases SET status=?, priority=?, assigned_to=?, tags=?,
               metadata=?, updated_at=?, resolved_at=? WHERE id=?""",
            (
                case.status.value, case.priority.value, case.assigned_to,
                json.dumps(case.tags), json.dumps(case.metadata, default=str),
                _iso(case.updated_at), _iso(case.resolved_at), case.id,
            ),
        )
        await db.commit()

    async def get_case(self, case_id: int) -> Case | None:
        db = await self._conn()
        async with db.execute("SELECT * FROM cases WHERE id=?", (case_id,)) as cur:
            row = await cur.fetchone()
            if not row:
                return None
            cols = [d[0] for d in cur.description]
            return self._row_to_case(dict(zip(cols, row)))

    async def list_cases(
        self,
        tenant: str,
        status: CaseStatus | None = None,
        contact_id: int | None = None,
        limit: int = 200,
    ) -> list[Case]:
        db = await self._conn()
        sql = "SELECT * FROM cases WHERE tenant=?"
        params: list[Any] = [tenant]
        if status is not None:
            sql += " AND status=?"
            params.append(status.value)
        if contact_id is not None:
            sql += " AND contact_id=?"
            params.append(contact_id)
        sql += " ORDER BY updated_at DESC LIMIT ?"
        params.append(limit)
        async with db.execute(sql, params) as cur:
            rows = await cur.fetchall()
            cols = [d[0] for d in cur.description]
            return [self._row_to_case(dict(zip(cols, row))) for row in rows]

    async def count_by_status(self, tenant: str) -> dict[str, int]:
        db = await self._conn()
        async with db.execute(
            "SELECT status, COUNT(*) FROM cases WHERE tenant=? GROUP BY status",
            (tenant,),
        ) as cur:
            rows = await cur.fetchall()
            return {row[0]: row[1] for row in rows}

    @staticmethod
    def _row_to_case(row: dict[str, Any]) -> Case:
        return Case(
            id=row["id"],
            tenant=row["tenant"],
            contact_id=row.get("contact_id"),
            subject=row.get("subject") or "",
            status=CaseStatus(row.get("status") or "new"),
            priority=CasePriority(row.get("priority") or "normal"),
            source=CaseSource(row.get("source") or "email_inbound"),
            assigned_to=row.get("assigned_to") or "",
            tags=json.loads(row.get("tags") or "[]"),
            metadata=json.loads(row.get("metadata") or "{}"),
            created_at=_parse_iso(row.get("created_at")) or datetime.utcnow(),
            updated_at=_parse_iso(row.get("updated_at")) or datetime.utcnow(),
            resolved_at=_parse_iso(row.get("resolved_at")),
        )

    # ------------------------------------------------------------------
    # Case Messages
    # ------------------------------------------------------------------

    async def add_message(self, msg: CaseMessage) -> int:
        db = await self._conn()
        cur = await db.execute(
            """INSERT INTO case_messages (case_id, tenant, direction, sender, recipient,
               subject, body, channel, metadata, occurred_at)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (
                msg.case_id, msg.tenant, msg.direction.value,
                msg.sender, msg.recipient, msg.subject, msg.body, msg.channel,
                json.dumps(msg.metadata, default=str), _iso(msg.occurred_at),
            ),
        )
        # Touch case updated_at
        await db.execute(
            "UPDATE cases SET updated_at=? WHERE id=?",
            (_iso(datetime.utcnow()), msg.case_id),
        )
        await db.commit()
        return cur.lastrowid or 0

    async def messages_for_case(
        self, case_id: int, limit: int = 200
    ) -> list[CaseMessage]:
        db = await self._conn()
        async with db.execute(
            "SELECT * FROM case_messages WHERE case_id=? ORDER BY occurred_at ASC LIMIT ?",
            (case_id, limit),
        ) as cur:
            rows = await cur.fetchall()
            cols = [d[0] for d in cur.description]
            return [self._row_to_message(dict(zip(cols, row))) for row in rows]

    @staticmethod
    def _row_to_message(row: dict[str, Any]) -> CaseMessage:
        return CaseMessage(
            id=row["id"],
            case_id=row["case_id"],
            tenant=row["tenant"],
            direction=CaseMessageDirection(row["direction"]),
            sender=row.get("sender") or "",
            recipient=row.get("recipient") or "",
            subject=row.get("subject") or "",
            body=row.get("body") or "",
            channel=row.get("channel") or "email",
            metadata=json.loads(row.get("metadata") or "{}"),
            occurred_at=_parse_iso(row.get("occurred_at")) or datetime.utcnow(),
        )
