"""SQLite-backed persistence for sales_ops.

Follows the pattern from `learning/patch_store.py`: aiosqlite async
connection, raw SQL schema strings, lazy initialization. No ORM.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import aiosqlite
import structlog

from sovereign_swarm.sales_ops.models import (
    Activity,
    ActivityType,
    Company,
    Contact,
    ContactSource,
    EnrollmentStatus,
    MessageChannel,
    MessageStatus,
    Opportunity,
    OpportunityStage,
    ScheduledMessage,
    SequenceEnrollment,
    deserialize_metadata,
    deserialize_tags,
    serialize_metadata,
    serialize_tags,
)

logger = structlog.get_logger()


_SCHEMA = """
CREATE TABLE IF NOT EXISTS companies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant TEXT NOT NULL,
    name TEXT NOT NULL,
    domain TEXT DEFAULT '',
    industry TEXT DEFAULT '',
    size TEXT DEFAULT '',
    region TEXT DEFAULT '',
    notes TEXT DEFAULT '',
    source TEXT DEFAULT 'manual',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS contacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant TEXT NOT NULL,
    company_id INTEGER REFERENCES companies(id),
    email TEXT DEFAULT '',
    phone TEXT DEFAULT '',
    first_name TEXT DEFAULT '',
    last_name TEXT DEFAULT '',
    role TEXT DEFAULT '',
    linkedin_url TEXT DEFAULT '',
    source TEXT DEFAULT 'manual',
    tags TEXT DEFAULT '[]',
    consent_sms INTEGER DEFAULT 0,
    unsubscribed INTEGER DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS opportunities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant TEXT NOT NULL,
    contact_id INTEGER NOT NULL REFERENCES contacts(id),
    company_id INTEGER REFERENCES companies(id),
    stage TEXT DEFAULT 'cold',
    value_cents INTEGER DEFAULT 0,
    close_date TEXT DEFAULT '',
    probability REAL DEFAULT 0.0,
    notes TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS activities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant TEXT NOT NULL,
    contact_id INTEGER NOT NULL REFERENCES contacts(id),
    opportunity_id INTEGER REFERENCES opportunities(id),
    type TEXT NOT NULL,
    channel TEXT DEFAULT '',
    subject TEXT DEFAULT '',
    body TEXT DEFAULT '',
    outcome TEXT DEFAULT '',
    metadata TEXT DEFAULT '{}',
    occurred_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sequence_enrollments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant TEXT NOT NULL,
    contact_id INTEGER NOT NULL REFERENCES contacts(id),
    sequence_name TEXT NOT NULL,
    current_step INTEGER DEFAULT 0,
    status TEXT DEFAULT 'active',
    exit_reason TEXT DEFAULT '',
    next_action_at TEXT,
    enrolled_at TEXT NOT NULL,
    completed_at TEXT
);

CREATE TABLE IF NOT EXISTS scheduled_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant TEXT NOT NULL,
    enrollment_id INTEGER NOT NULL REFERENCES sequence_enrollments(id),
    contact_id INTEGER NOT NULL REFERENCES contacts(id),
    step_index INTEGER NOT NULL,
    channel TEXT NOT NULL,
    subject TEXT DEFAULT '',
    body TEXT DEFAULT '',
    status TEXT DEFAULT 'drafted',
    scheduled_for TEXT,
    approved_at TEXT,
    sent_at TEXT,
    reply_received_at TEXT,
    error TEXT DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_contacts_tenant ON contacts(tenant);
CREATE INDEX IF NOT EXISTS idx_contacts_email ON contacts(email);
CREATE INDEX IF NOT EXISTS idx_activities_contact ON activities(contact_id);
CREATE INDEX IF NOT EXISTS idx_enrollments_next ON sequence_enrollments(next_action_at, status);
CREATE INDEX IF NOT EXISTS idx_msg_status ON scheduled_messages(status, scheduled_for);
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


class SalesOpsStore:
    """SQLite persistence for sales_ops."""

    def __init__(self, db_path: str | Path = "data/sales_ops.db") -> None:
        self.db_path = Path(db_path)
        self._db: aiosqlite.Connection | None = None

    async def initialize(self) -> None:
        """Create tables if missing."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(str(self.db_path))
        await self._db.executescript(_SCHEMA)
        await self._db.commit()
        logger.info("sales_ops.store.initialized", db_path=str(self.db_path))

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
    # Companies
    # ------------------------------------------------------------------

    async def upsert_company(self, company: Company) -> int:
        db = await self._conn()
        if company.id is not None:
            await db.execute(
                """UPDATE companies SET tenant=?, name=?, domain=?, industry=?,
                   size=?, region=?, notes=?, source=? WHERE id=?""",
                (
                    company.tenant, company.name, company.domain, company.industry,
                    company.size, company.region, company.notes, company.source.value,
                    company.id,
                ),
            )
            await db.commit()
            return company.id

        # Dedupe by (tenant, domain) or (tenant, name)
        if company.domain:
            async with db.execute(
                "SELECT id FROM companies WHERE tenant=? AND domain=?",
                (company.tenant, company.domain),
            ) as cur:
                row = await cur.fetchone()
                if row:
                    company.id = row[0]
                    return await self.upsert_company(company)

        cur = await db.execute(
            """INSERT INTO companies (tenant, name, domain, industry, size, region, notes, source, created_at)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (
                company.tenant, company.name, company.domain, company.industry,
                company.size, company.region, company.notes, company.source.value,
                _iso(company.created_at),
            ),
        )
        await db.commit()
        return cur.lastrowid or 0

    async def get_company(self, company_id: int) -> Company | None:
        db = await self._conn()
        async with db.execute("SELECT * FROM companies WHERE id=?", (company_id,)) as cur:
            row = await cur.fetchone()
            if not row:
                return None
            cols = [d[0] for d in cur.description]
            return self._row_to_company(dict(zip(cols, row)))

    async def list_companies(self, tenant: str, limit: int = 100) -> list[Company]:
        db = await self._conn()
        async with db.execute(
            "SELECT * FROM companies WHERE tenant=? ORDER BY created_at DESC LIMIT ?",
            (tenant, limit),
        ) as cur:
            rows = await cur.fetchall()
            cols = [d[0] for d in cur.description]
            return [self._row_to_company(dict(zip(cols, row))) for row in rows]

    @staticmethod
    def _row_to_company(row: dict[str, Any]) -> Company:
        return Company(
            id=row["id"],
            tenant=row["tenant"],
            name=row["name"],
            domain=row.get("domain") or "",
            industry=row.get("industry") or "",
            size=row.get("size") or "",
            region=row.get("region") or "",
            notes=row.get("notes") or "",
            source=ContactSource(row.get("source") or "manual"),
            created_at=_parse_iso(row.get("created_at")) or datetime.utcnow(),
        )

    # ------------------------------------------------------------------
    # Contacts
    # ------------------------------------------------------------------

    async def upsert_contact(self, contact: Contact) -> int:
        db = await self._conn()
        contact.updated_at = datetime.utcnow()
        if contact.id is not None:
            await db.execute(
                """UPDATE contacts SET tenant=?, company_id=?, email=?, phone=?,
                   first_name=?, last_name=?, role=?, linkedin_url=?, source=?,
                   tags=?, consent_sms=?, unsubscribed=?, updated_at=? WHERE id=?""",
                (
                    contact.tenant, contact.company_id, contact.email, contact.phone,
                    contact.first_name, contact.last_name, contact.role, contact.linkedin_url,
                    contact.source.value, serialize_tags(contact.tags),
                    int(contact.consent_sms), int(contact.unsubscribed),
                    _iso(contact.updated_at), contact.id,
                ),
            )
            await db.commit()
            return contact.id

        # Dedupe by (tenant, email)
        if contact.email:
            async with db.execute(
                "SELECT id FROM contacts WHERE tenant=? AND email=?",
                (contact.tenant, contact.email),
            ) as cur:
                row = await cur.fetchone()
                if row:
                    contact.id = row[0]
                    return await self.upsert_contact(contact)

        cur = await db.execute(
            """INSERT INTO contacts (tenant, company_id, email, phone, first_name, last_name,
               role, linkedin_url, source, tags, consent_sms, unsubscribed, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                contact.tenant, contact.company_id, contact.email, contact.phone,
                contact.first_name, contact.last_name, contact.role, contact.linkedin_url,
                contact.source.value, serialize_tags(contact.tags),
                int(contact.consent_sms), int(contact.unsubscribed),
                _iso(contact.created_at), _iso(contact.updated_at),
            ),
        )
        await db.commit()
        return cur.lastrowid or 0

    async def get_contact(self, contact_id: int) -> Contact | None:
        db = await self._conn()
        async with db.execute("SELECT * FROM contacts WHERE id=?", (contact_id,)) as cur:
            row = await cur.fetchone()
            if not row:
                return None
            cols = [d[0] for d in cur.description]
            return self._row_to_contact(dict(zip(cols, row)))

    async def list_contacts(
        self, tenant: str, limit: int = 100, company_id: int | None = None
    ) -> list[Contact]:
        db = await self._conn()
        sql = "SELECT * FROM contacts WHERE tenant=?"
        params: list[Any] = [tenant]
        if company_id is not None:
            sql += " AND company_id=?"
            params.append(company_id)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        async with db.execute(sql, params) as cur:
            rows = await cur.fetchall()
            cols = [d[0] for d in cur.description]
            return [self._row_to_contact(dict(zip(cols, row))) for row in rows]

    async def mark_unsubscribed(self, contact_id: int) -> None:
        db = await self._conn()
        await db.execute(
            "UPDATE contacts SET unsubscribed=1, updated_at=? WHERE id=?",
            (_iso(datetime.utcnow()), contact_id),
        )
        await db.commit()

    @staticmethod
    def _row_to_contact(row: dict[str, Any]) -> Contact:
        return Contact(
            id=row["id"],
            tenant=row["tenant"],
            company_id=row.get("company_id"),
            email=row.get("email") or "",
            phone=row.get("phone") or "",
            first_name=row.get("first_name") or "",
            last_name=row.get("last_name") or "",
            role=row.get("role") or "",
            linkedin_url=row.get("linkedin_url") or "",
            source=ContactSource(row.get("source") or "manual"),
            tags=deserialize_tags(row.get("tags")),
            consent_sms=bool(row.get("consent_sms")),
            unsubscribed=bool(row.get("unsubscribed")),
            created_at=_parse_iso(row.get("created_at")) or datetime.utcnow(),
            updated_at=_parse_iso(row.get("updated_at")) or datetime.utcnow(),
        )

    # ------------------------------------------------------------------
    # Activities
    # ------------------------------------------------------------------

    async def log_activity(self, activity: Activity) -> int:
        db = await self._conn()
        cur = await db.execute(
            """INSERT INTO activities (tenant, contact_id, opportunity_id, type, channel,
               subject, body, outcome, metadata, occurred_at)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (
                activity.tenant, activity.contact_id, activity.opportunity_id,
                activity.type.value, activity.channel, activity.subject, activity.body,
                activity.outcome, serialize_metadata(activity.metadata),
                _iso(activity.occurred_at),
            ),
        )
        await db.commit()
        return cur.lastrowid or 0

    async def activities_for_contact(self, contact_id: int, limit: int = 100) -> list[Activity]:
        db = await self._conn()
        async with db.execute(
            "SELECT * FROM activities WHERE contact_id=? ORDER BY occurred_at DESC LIMIT ?",
            (contact_id, limit),
        ) as cur:
            rows = await cur.fetchall()
            cols = [d[0] for d in cur.description]
            return [self._row_to_activity(dict(zip(cols, row))) for row in rows]

    @staticmethod
    def _row_to_activity(row: dict[str, Any]) -> Activity:
        return Activity(
            id=row["id"],
            tenant=row["tenant"],
            contact_id=row["contact_id"],
            opportunity_id=row.get("opportunity_id"),
            type=ActivityType(row["type"]),
            channel=row.get("channel") or "",
            subject=row.get("subject") or "",
            body=row.get("body") or "",
            outcome=row.get("outcome") or "",
            metadata=deserialize_metadata(row.get("metadata")),
            occurred_at=_parse_iso(row.get("occurred_at")) or datetime.utcnow(),
        )

    # ------------------------------------------------------------------
    # Enrollments
    # ------------------------------------------------------------------

    async def create_enrollment(self, enrollment: SequenceEnrollment) -> int:
        db = await self._conn()
        cur = await db.execute(
            """INSERT INTO sequence_enrollments (tenant, contact_id, sequence_name,
               current_step, status, exit_reason, next_action_at, enrolled_at, completed_at)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (
                enrollment.tenant, enrollment.contact_id, enrollment.sequence_name,
                enrollment.current_step, enrollment.status.value, enrollment.exit_reason,
                _iso(enrollment.next_action_at), _iso(enrollment.enrolled_at),
                _iso(enrollment.completed_at),
            ),
        )
        await db.commit()
        return cur.lastrowid or 0

    async def update_enrollment(self, enrollment: SequenceEnrollment) -> None:
        db = await self._conn()
        await db.execute(
            """UPDATE sequence_enrollments SET current_step=?, status=?, exit_reason=?,
               next_action_at=?, completed_at=? WHERE id=?""",
            (
                enrollment.current_step, enrollment.status.value, enrollment.exit_reason,
                _iso(enrollment.next_action_at), _iso(enrollment.completed_at),
                enrollment.id,
            ),
        )
        await db.commit()

    async def get_enrollment(self, enrollment_id: int) -> SequenceEnrollment | None:
        db = await self._conn()
        async with db.execute(
            "SELECT * FROM sequence_enrollments WHERE id=?", (enrollment_id,)
        ) as cur:
            row = await cur.fetchone()
            if not row:
                return None
            cols = [d[0] for d in cur.description]
            return self._row_to_enrollment(dict(zip(cols, row)))

    async def due_enrollments(self, tenant: str | None = None) -> list[SequenceEnrollment]:
        """Return active enrollments whose next_action_at is now or past."""
        db = await self._conn()
        now = _iso(datetime.utcnow())
        sql = (
            "SELECT * FROM sequence_enrollments WHERE status='active' "
            "AND (next_action_at IS NULL OR next_action_at <= ?)"
        )
        params: list[Any] = [now]
        if tenant:
            sql += " AND tenant=?"
            params.append(tenant)
        async with db.execute(sql, params) as cur:
            rows = await cur.fetchall()
            cols = [d[0] for d in cur.description]
            return [self._row_to_enrollment(dict(zip(cols, row))) for row in rows]

    async def list_enrollments(
        self,
        tenant: str,
        status: EnrollmentStatus | None = None,
        limit: int = 200,
    ) -> list[SequenceEnrollment]:
        db = await self._conn()
        sql = "SELECT * FROM sequence_enrollments WHERE tenant=?"
        params: list[Any] = [tenant]
        if status is not None:
            sql += " AND status=?"
            params.append(status.value)
        sql += " ORDER BY enrolled_at DESC LIMIT ?"
        params.append(limit)
        async with db.execute(sql, params) as cur:
            rows = await cur.fetchall()
            cols = [d[0] for d in cur.description]
            return [self._row_to_enrollment(dict(zip(cols, row))) for row in rows]

    @staticmethod
    def _row_to_enrollment(row: dict[str, Any]) -> SequenceEnrollment:
        return SequenceEnrollment(
            id=row["id"],
            tenant=row["tenant"],
            contact_id=row["contact_id"],
            sequence_name=row["sequence_name"],
            current_step=row.get("current_step") or 0,
            status=EnrollmentStatus(row.get("status") or "active"),
            exit_reason=row.get("exit_reason") or "",
            next_action_at=_parse_iso(row.get("next_action_at")),
            enrolled_at=_parse_iso(row.get("enrolled_at")) or datetime.utcnow(),
            completed_at=_parse_iso(row.get("completed_at")),
        )

    # ------------------------------------------------------------------
    # Scheduled messages
    # ------------------------------------------------------------------

    async def create_message(self, msg: ScheduledMessage) -> int:
        db = await self._conn()
        cur = await db.execute(
            """INSERT INTO scheduled_messages (tenant, enrollment_id, contact_id, step_index,
               channel, subject, body, status, scheduled_for, approved_at, sent_at,
               reply_received_at, error, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                msg.tenant, msg.enrollment_id, msg.contact_id, msg.step_index,
                msg.channel.value, msg.subject, msg.body, msg.status.value,
                _iso(msg.scheduled_for), _iso(msg.approved_at), _iso(msg.sent_at),
                _iso(msg.reply_received_at), msg.error, _iso(msg.created_at),
            ),
        )
        await db.commit()
        return cur.lastrowid or 0

    async def update_message(self, msg: ScheduledMessage) -> None:
        db = await self._conn()
        await db.execute(
            """UPDATE scheduled_messages SET status=?, subject=?, body=?,
               approved_at=?, sent_at=?, reply_received_at=?, error=? WHERE id=?""",
            (
                msg.status.value, msg.subject, msg.body,
                _iso(msg.approved_at), _iso(msg.sent_at),
                _iso(msg.reply_received_at), msg.error, msg.id,
            ),
        )
        await db.commit()

    async def get_message(self, message_id: int) -> ScheduledMessage | None:
        db = await self._conn()
        async with db.execute(
            "SELECT * FROM scheduled_messages WHERE id=?", (message_id,)
        ) as cur:
            row = await cur.fetchone()
            if not row:
                return None
            cols = [d[0] for d in cur.description]
            return self._row_to_message(dict(zip(cols, row)))

    async def pending_messages(
        self, tenant: str | None = None, status: MessageStatus = MessageStatus.DRAFTED
    ) -> list[ScheduledMessage]:
        db = await self._conn()
        sql = "SELECT * FROM scheduled_messages WHERE status=?"
        params: list[Any] = [status.value]
        if tenant:
            sql += " AND tenant=?"
            params.append(tenant)
        sql += " ORDER BY created_at ASC LIMIT 500"
        async with db.execute(sql, params) as cur:
            rows = await cur.fetchall()
            cols = [d[0] for d in cur.description]
            return [self._row_to_message(dict(zip(cols, row))) for row in rows]

    @staticmethod
    def _row_to_message(row: dict[str, Any]) -> ScheduledMessage:
        return ScheduledMessage(
            id=row["id"],
            tenant=row["tenant"],
            enrollment_id=row["enrollment_id"],
            contact_id=row["contact_id"],
            step_index=row["step_index"],
            channel=MessageChannel(row["channel"]),
            subject=row.get("subject") or "",
            body=row.get("body") or "",
            status=MessageStatus(row.get("status") or "drafted"),
            scheduled_for=_parse_iso(row.get("scheduled_for")),
            approved_at=_parse_iso(row.get("approved_at")),
            sent_at=_parse_iso(row.get("sent_at")),
            reply_received_at=_parse_iso(row.get("reply_received_at")),
            error=row.get("error") or "",
            created_at=_parse_iso(row.get("created_at")) or datetime.utcnow(),
        )
