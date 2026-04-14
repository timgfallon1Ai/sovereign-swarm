"""CaseService — high-level case lifecycle management."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import structlog

from sovereign_swarm.support.models import (
    Case,
    CaseMessage,
    CaseMessageDirection,
    CasePriority,
    CaseSource,
    CaseStatus,
)
from sovereign_swarm.support.store import SupportStore

logger = structlog.get_logger()


class CaseService:
    """Business logic for cases: create, reply, assign, resolve."""

    def __init__(self, store: SupportStore) -> None:
        self.store = store

    async def create_from_inbound_email(
        self,
        tenant: str,
        sender: str,
        subject: str,
        body: str,
        contact_id: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Case:
        """Create a new case from an inbound email."""
        case = Case(
            tenant=tenant,
            contact_id=contact_id,
            subject=subject or "(no subject)",
            status=CaseStatus.NEW,
            priority=CasePriority.NORMAL,
            source=CaseSource.EMAIL_INBOUND,
            metadata=metadata or {},
        )
        case.id = await self.store.create_case(case)

        # Add the inbound message as the first case message
        msg = CaseMessage(
            case_id=case.id,
            tenant=tenant,
            direction=CaseMessageDirection.INBOUND,
            sender=sender,
            subject=subject,
            body=body,
            channel="email",
        )
        await self.store.add_message(msg)
        return case

    async def create_manual(
        self,
        tenant: str,
        subject: str,
        contact_id: int | None = None,
        priority: CasePriority = CasePriority.NORMAL,
        assigned_to: str = "",
    ) -> Case:
        case = Case(
            tenant=tenant,
            contact_id=contact_id,
            subject=subject,
            status=CaseStatus.NEW,
            priority=priority,
            source=CaseSource.MANUAL,
            assigned_to=assigned_to,
        )
        case.id = await self.store.create_case(case)
        return case

    async def reply(
        self,
        case_id: int,
        tenant: str,
        direction: CaseMessageDirection,
        body: str,
        sender: str = "",
        subject: str = "",
        channel: str = "email",
    ) -> CaseMessage:
        """Add a reply (inbound or outbound) to a case."""
        case = await self.store.get_case(case_id)
        if case is None:
            raise ValueError(f"Case {case_id} not found")
        if case.tenant != tenant:
            raise ValueError(f"Case {case_id} tenant mismatch")

        msg = CaseMessage(
            case_id=case_id,
            tenant=tenant,
            direction=direction,
            sender=sender,
            subject=subject or case.subject,
            body=body,
            channel=channel,
        )
        await self.store.add_message(msg)

        # On outbound reply, transition to PENDING (waiting on customer)
        # On inbound reply to a PENDING/RESOLVED case, reopen to OPEN
        if direction == CaseMessageDirection.OUTBOUND:
            if case.status in (CaseStatus.NEW, CaseStatus.OPEN):
                case.status = CaseStatus.PENDING
                await self.store.update_case(case)
        elif direction == CaseMessageDirection.INBOUND:
            if case.status in (CaseStatus.PENDING, CaseStatus.RESOLVED):
                case.status = CaseStatus.OPEN
                case.resolved_at = None
                await self.store.update_case(case)

        return msg

    async def resolve(self, case_id: int, tenant: str, note: str = "") -> Case:
        case = await self.store.get_case(case_id)
        if case is None or case.tenant != tenant:
            raise ValueError(f"Case {case_id} not found or tenant mismatch")
        case.status = CaseStatus.RESOLVED
        case.resolved_at = datetime.utcnow()
        if note:
            case.metadata["resolution_note"] = note
        await self.store.update_case(case)
        logger.info("support.case_resolved", case_id=case_id, tenant=tenant)
        return case

    async def assign(self, case_id: int, tenant: str, assignee: str) -> Case:
        case = await self.store.get_case(case_id)
        if case is None or case.tenant != tenant:
            raise ValueError(f"Case {case_id} not found or tenant mismatch")
        case.assigned_to = assignee
        if case.status == CaseStatus.NEW:
            case.status = CaseStatus.OPEN
        await self.store.update_case(case)
        return case

    async def pipeline_summary(self, tenant: str) -> dict[str, int]:
        return await self.store.count_by_status(tenant)
