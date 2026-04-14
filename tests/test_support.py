"""Tests for the support module (cases + messages)."""

from __future__ import annotations

from pathlib import Path

import pytest

from sovereign_swarm.support.models import (
    Case,
    CaseMessage,
    CaseMessageDirection,
    CasePriority,
    CaseSource,
    CaseStatus,
)
from sovereign_swarm.support.service import CaseService
from sovereign_swarm.support.store import SupportStore


async def _new_store(tmp_path: Path) -> SupportStore:
    s = SupportStore(db_path=str(tmp_path / "support.db"))
    await s.initialize()
    return s


class TestSupportStore:
    @pytest.mark.asyncio
    async def test_create_and_get_case(self, tmp_path: Path):
        s = await _new_store(tmp_path)
        case = Case(
            tenant="atx_mats",
            subject="Damaged mat on delivery",
            source=CaseSource.EMAIL_INBOUND,
        )
        case_id = await s.create_case(case)
        got = await s.get_case(case_id)
        assert got is not None
        assert got.subject == "Damaged mat on delivery"
        assert got.status == CaseStatus.NEW
        await s.close()

    @pytest.mark.asyncio
    async def test_add_message_and_fetch_thread(self, tmp_path: Path):
        s = await _new_store(tmp_path)
        case_id = await s.create_case(Case(
            tenant="atx_mats",
            subject="Warranty question",
        ))
        await s.add_message(CaseMessage(
            case_id=case_id, tenant="atx_mats",
            direction=CaseMessageDirection.INBOUND,
            sender="customer@example.com", body="Is this covered?",
        ))
        await s.add_message(CaseMessage(
            case_id=case_id, tenant="atx_mats",
            direction=CaseMessageDirection.OUTBOUND,
            sender="tim@atxmats.com", body="Yes, 10-year warranty.",
        ))
        msgs = await s.messages_for_case(case_id)
        assert len(msgs) == 2
        assert msgs[0].direction == CaseMessageDirection.INBOUND
        assert msgs[1].direction == CaseMessageDirection.OUTBOUND
        await s.close()

    @pytest.mark.asyncio
    async def test_count_by_status(self, tmp_path: Path):
        s = await _new_store(tmp_path)
        for status in (CaseStatus.NEW, CaseStatus.NEW, CaseStatus.OPEN):
            await s.create_case(Case(
                tenant="atx_mats", subject="x", status=status,
            ))
        counts = await s.count_by_status("atx_mats")
        assert counts.get("new") == 2
        assert counts.get("open") == 1
        await s.close()


class TestCaseService:
    @pytest.mark.asyncio
    async def test_create_from_inbound(self, tmp_path: Path):
        s = await _new_store(tmp_path)
        svc = CaseService(s)
        case = await svc.create_from_inbound_email(
            tenant="atx_mats",
            sender="acme@example.com",
            subject="Quote request",
            body="Can you spec flooring for 50k sqft?",
        )
        assert case.id is not None
        msgs = await s.messages_for_case(case.id)
        assert len(msgs) == 1
        assert msgs[0].direction == CaseMessageDirection.INBOUND
        await s.close()

    @pytest.mark.asyncio
    async def test_outbound_reply_moves_to_pending(self, tmp_path: Path):
        s = await _new_store(tmp_path)
        svc = CaseService(s)
        case = await svc.create_from_inbound_email(
            tenant="atx_mats", sender="c@e.com", subject="Q", body="B",
        )
        await svc.reply(
            case_id=case.id, tenant="atx_mats",
            direction=CaseMessageDirection.OUTBOUND,
            body="Reply from us",
        )
        updated = await s.get_case(case.id)
        assert updated.status == CaseStatus.PENDING
        await s.close()

    @pytest.mark.asyncio
    async def test_inbound_reply_reopens_resolved(self, tmp_path: Path):
        s = await _new_store(tmp_path)
        svc = CaseService(s)
        case = await svc.create_from_inbound_email(
            tenant="atx_mats", sender="c@e.com", subject="Q", body="B",
        )
        await svc.resolve(case.id, "atx_mats", note="fixed")
        # New inbound after resolve should reopen
        await svc.reply(
            case_id=case.id, tenant="atx_mats",
            direction=CaseMessageDirection.INBOUND,
            sender="c@e.com", body="Still broken",
        )
        updated = await s.get_case(case.id)
        assert updated.status == CaseStatus.OPEN
        assert updated.resolved_at is None
        await s.close()

    @pytest.mark.asyncio
    async def test_resolve_and_assign(self, tmp_path: Path):
        s = await _new_store(tmp_path)
        svc = CaseService(s)
        case = await svc.create_manual(
            tenant="atx_mats", subject="Call back", assigned_to="",
        )
        assigned = await svc.assign(case.id, "atx_mats", "tim@atxmats.com")
        assert assigned.assigned_to == "tim@atxmats.com"
        assert assigned.status == CaseStatus.OPEN

        resolved = await svc.resolve(case.id, "atx_mats", note="Called back")
        assert resolved.status == CaseStatus.RESOLVED
        assert resolved.resolved_at is not None
        assert resolved.metadata.get("resolution_note") == "Called back"
        await s.close()
