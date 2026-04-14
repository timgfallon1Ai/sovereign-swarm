"""Tests for sales_ops module.

Covers: models, store CRUD, sequence template registry, sequencer flow
(enroll → tick → drafted message), approval queue dispatch paths,
and agent registry integration.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from sovereign_swarm.sales_ops.models import (
    Activity,
    ActivityType,
    Company,
    Contact,
    ContactSource,
    EnrollmentStatus,
    MessageChannel,
    MessageStatus,
    ScheduledMessage,
    deserialize_tags,
    serialize_tags,
)
from sovereign_swarm.sales_ops.sequences import (
    get_sequence,
    list_sequences,
    render_template,
)
from sovereign_swarm.sales_ops.sequencer import Sequencer
from sovereign_swarm.sales_ops.approval_queue import ApprovalQueue
from sovereign_swarm.sales_ops.store import SalesOpsStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _new_store(tmp_path: Path) -> SalesOpsStore:
    s = SalesOpsStore(db_path=str(tmp_path / "sales_ops.db"))
    await s.initialize()
    return s


def _sample_contact() -> Contact:
    return Contact(
        tenant="atx_mats",
        email="tim@example.com",
        first_name="Tim",
        last_name="Test",
        role="facility manager",
        source=ContactSource.MANUAL,
        tags=["pilot"],
    )


def _sample_company() -> Company:
    return Company(
        tenant="atx_mats",
        name="Test Industries",
        domain="example.com",
        source=ContactSource.MANUAL,
    )


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class TestModels:
    def test_contact_full_name(self):
        c = Contact(tenant="x", first_name="Ada", last_name="Lovelace")
        assert c.full_name == "Ada Lovelace"

    def test_contact_display_with_role(self):
        c = Contact(tenant="x", first_name="Ada", last_name="Lovelace", role="CTO")
        assert "Ada Lovelace (CTO)" in c.display

    def test_tag_serialization_roundtrip(self):
        raw = serialize_tags(["a", "b", "c"])
        assert deserialize_tags(raw) == ["a", "b", "c"]

    def test_deserialize_empty_tags(self):
        assert deserialize_tags(None) == []
        assert deserialize_tags("") == []
        assert deserialize_tags("not json") == []

    def test_opportunity_value_usd(self):
        from sovereign_swarm.sales_ops.models import Opportunity
        o = Opportunity(tenant="x", contact_id=1, value_cents=150000)
        assert o.value_usd == 1500.0


# ---------------------------------------------------------------------------
# Store CRUD
# ---------------------------------------------------------------------------


class TestStore:
    @pytest.mark.asyncio
    async def test_store_initialize_creates_db(self, tmp_path: Path):
        s = SalesOpsStore(db_path=str(tmp_path / "x.db"))
        await s.initialize()
        assert (tmp_path / "x.db").exists()
        await s.close()

    @pytest.mark.asyncio
    async def test_upsert_company_dedupe(self, tmp_path: Path):
        s = await _new_store(tmp_path)
        cid1 = await s.upsert_company(_sample_company())
        cid2 = await s.upsert_company(_sample_company())
        assert cid1 == cid2
        await s.close()

    @pytest.mark.asyncio
    async def test_upsert_contact_dedupe_by_email(self, tmp_path: Path):
        s = await _new_store(tmp_path)
        cid1 = await s.upsert_contact(_sample_contact())
        cid2 = await s.upsert_contact(_sample_contact())
        assert cid1 == cid2
        await s.close()

    @pytest.mark.asyncio
    async def test_get_contact_roundtrip(self, tmp_path: Path):
        s = await _new_store(tmp_path)
        cid = await s.upsert_contact(_sample_contact())
        got = await s.get_contact(cid)
        assert got is not None
        assert got.email == "tim@example.com"
        assert got.tags == ["pilot"]
        await s.close()

    @pytest.mark.asyncio
    async def test_list_contacts_by_tenant(self, tmp_path: Path):
        s = await _new_store(tmp_path)
        await s.upsert_contact(_sample_contact())
        await s.upsert_contact(Contact(
            tenant="gbb", email="other@example.com", first_name="Other",
        ))
        atx = await s.list_contacts("atx_mats")
        gbb = await s.list_contacts("gbb")
        assert len(atx) == 1
        assert len(gbb) == 1
        await s.close()

    @pytest.mark.asyncio
    async def test_log_activity(self, tmp_path: Path):
        s = await _new_store(tmp_path)
        cid = await s.upsert_contact(_sample_contact())
        aid = await s.log_activity(Activity(
            tenant="atx_mats",
            contact_id=cid,
            type=ActivityType.EMAIL_SENT,
            subject="Test",
            body="Hello",
        ))
        assert aid > 0
        got = await s.activities_for_contact(cid)
        assert len(got) == 1
        assert got[0].type == ActivityType.EMAIL_SENT
        await s.close()

    @pytest.mark.asyncio
    async def test_mark_unsubscribed(self, tmp_path: Path):
        s = await _new_store(tmp_path)
        cid = await s.upsert_contact(_sample_contact())
        await s.mark_unsubscribed(cid)
        got = await s.get_contact(cid)
        assert got.unsubscribed is True
        await s.close()


# ---------------------------------------------------------------------------
# Sequence templates (no DB needed)
# ---------------------------------------------------------------------------


class TestSequences:
    def test_atx_distributor_registered(self):
        tmpl = get_sequence("atx_distributor")
        assert tmpl is not None
        assert tmpl.tenant == "atx_mats"

    def test_atx_distributor_step_count(self):
        tmpl = get_sequence("atx_distributor")
        assert tmpl.length >= 25  # ~28 touchpoints

    def test_step_indices_sequential(self):
        tmpl = get_sequence("atx_distributor")
        for i, step in enumerate(tmpl.steps):
            assert step.index == i

    def test_day_offsets_monotonic(self):
        tmpl = get_sequence("atx_distributor")
        prev = -1
        for step in tmpl.steps:
            assert step.day_offset >= prev
            prev = step.day_offset

    def test_list_sequences_by_tenant(self):
        atx = list_sequences("atx_mats")
        assert len(atx) >= 1

    def test_render_template_fills_placeholders(self):
        contact = Contact(tenant="x", first_name="Ada", last_name="Lovelace", role="CTO")
        out = render_template(
            "Hi {first_name}, saw {role} at {company}",
            contact,
            None,
        )
        assert "Ada" in out
        assert "CTO" in out
        assert "{first_name}" not in out

    def test_safe_steps_exist(self):
        tmpl = get_sequence("atx_distributor")
        for step in tmpl.steps[:3]:
            assert not step.requires_explicit_approval

    def test_sms_step_requires_explicit(self):
        tmpl = get_sequence("atx_distributor")
        for step in tmpl.steps:
            if step.channel == MessageChannel.SMS:
                assert step.requires_explicit_approval


# ---------------------------------------------------------------------------
# Sequencer
# ---------------------------------------------------------------------------


class TestSequencer:
    @pytest.mark.asyncio
    async def test_enroll_creates_enrollment(self, tmp_path: Path):
        s = await _new_store(tmp_path)
        cid = await s.upsert_contact(_sample_contact())
        seq = Sequencer(s)
        enrollment = await seq.enroll("atx_mats", cid, "atx_distributor")
        assert enrollment is not None
        assert enrollment.status == EnrollmentStatus.ACTIVE
        assert enrollment.current_step == 0
        await s.close()

    @pytest.mark.asyncio
    async def test_enroll_rejects_tenant_mismatch(self, tmp_path: Path):
        s = await _new_store(tmp_path)
        cid = await s.upsert_contact(_sample_contact())
        seq = Sequencer(s)
        result = await seq.enroll("gbb", cid, "atx_distributor")
        assert result is None
        await s.close()

    @pytest.mark.asyncio
    async def test_enroll_rejects_unsubscribed(self, tmp_path: Path):
        s = await _new_store(tmp_path)
        c = Contact(tenant="atx_mats", email="stop@example.com", unsubscribed=True)
        cid = await s.upsert_contact(c)
        seq = Sequencer(s)
        result = await seq.enroll("atx_mats", cid, "atx_distributor")
        assert result is None
        await s.close()

    @pytest.mark.asyncio
    async def test_tick_drafts_first_message(self, tmp_path: Path):
        s = await _new_store(tmp_path)
        cid = await s.upsert_contact(_sample_contact())
        seq = Sequencer(s)
        await seq.enroll("atx_mats", cid, "atx_distributor")
        msgs = await seq.tick()
        assert len(msgs) == 1
        assert msgs[0].status == MessageStatus.DRAFTED
        assert msgs[0].step_index == 0
        await s.close()

    @pytest.mark.asyncio
    async def test_tick_advances_enrollment(self, tmp_path: Path):
        s = await _new_store(tmp_path)
        cid = await s.upsert_contact(_sample_contact())
        seq = Sequencer(s)
        enrollment = await seq.enroll("atx_mats", cid, "atx_distributor")
        await seq.tick()
        updated = await s.get_enrollment(enrollment.id)
        assert updated.current_step == 1
        await s.close()

    @pytest.mark.asyncio
    async def test_pause_on_reply(self, tmp_path: Path):
        s = await _new_store(tmp_path)
        cid = await s.upsert_contact(_sample_contact())
        seq = Sequencer(s)
        await seq.enroll("atx_mats", cid, "atx_distributor")
        count = await seq.pause_on_reply(cid)
        assert count == 1
        paused = await s.list_enrollments("atx_mats", status=EnrollmentStatus.PAUSED)
        assert len(paused) == 1
        await s.close()


# ---------------------------------------------------------------------------
# Approval queue
# ---------------------------------------------------------------------------


class TestApprovalQueue:
    @pytest.mark.asyncio
    async def test_pending_returns_drafted(self, tmp_path: Path):
        s = await _new_store(tmp_path)
        cid = await s.upsert_contact(_sample_contact())
        seq = Sequencer(s)
        await seq.enroll("atx_mats", cid, "atx_distributor")
        await seq.tick()
        queue = ApprovalQueue(s)
        pending = await queue.pending()
        assert len(pending) == 1
        await s.close()

    @pytest.mark.asyncio
    async def test_skip_marks_skipped(self, tmp_path: Path):
        s = await _new_store(tmp_path)
        cid = await s.upsert_contact(_sample_contact())
        seq = Sequencer(s)
        await seq.enroll("atx_mats", cid, "atx_distributor")
        msgs = await seq.tick()
        queue = ApprovalQueue(s)
        ok = await queue.skip(msgs[0].id, reason="testing")
        assert ok
        got = await s.get_message(msgs[0].id)
        assert got.status == MessageStatus.SKIPPED
        await s.close()

    @pytest.mark.asyncio
    async def test_approve_all_safe_respects_explicit_approval(self, tmp_path: Path):
        """Messages on steps with requires_explicit_approval=True must NOT be auto-approved."""
        s = await _new_store(tmp_path)
        cid = await s.upsert_contact(_sample_contact())
        seq = Sequencer(s)
        enrollment = await seq.enroll("atx_mats", cid, "atx_distributor")

        # Step 3 (index 3) of atx_distributor is the "social proof + sample" email,
        # which requires_explicit_approval=True in our template.
        unsafe = ScheduledMessage(
            tenant="atx_mats",
            enrollment_id=enrollment.id,
            contact_id=cid,
            step_index=3,
            channel=MessageChannel.EMAIL,
            subject="ROI ask",
            body="Body",
            status=MessageStatus.DRAFTED,
        )
        unsafe.id = await s.create_message(unsafe)

        queue = ApprovalQueue(s)
        stats = await queue.approve_all_safe(tenant="atx_mats")
        assert stats["skipped_unsafe"] >= 1

        got = await s.get_message(unsafe.id)
        assert got.status == MessageStatus.DRAFTED  # stayed drafted
        await s.close()


# ---------------------------------------------------------------------------
# Registry integration
# ---------------------------------------------------------------------------


class TestRegistryIntegration:
    def test_sales_ops_registered(self):
        from sovereign_swarm.protocol.registry import bootstrap_default_registry
        registry = bootstrap_default_registry()
        names = [c.name for c in registry.list_agents()]
        assert "sales_ops" in names

    def test_agent_card_has_expected_intents(self):
        from sovereign_swarm.sales_ops.agent import SalesOpsAgent
        agent = SalesOpsAgent()
        intents = agent.card.supported_intents
        for required in ("prospect", "enroll", "queue", "approve", "pipeline"):
            assert required in intents
