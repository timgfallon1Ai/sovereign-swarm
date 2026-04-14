"""Tests for the analytics module."""

from __future__ import annotations

from pathlib import Path

import pytest

from sovereign_swarm.analytics import (
    channel_metrics,
    funnel_metrics,
    sequence_metrics,
)
from sovereign_swarm.sales_ops.models import (
    Activity,
    ActivityType,
    Contact,
    ContactSource,
    Opportunity,
    OpportunityStage,
)
from sovereign_swarm.sales_ops.sequencer import Sequencer
from sovereign_swarm.sales_ops.store import SalesOpsStore


async def _new_store(tmp_path: Path) -> SalesOpsStore:
    s = SalesOpsStore(db_path=str(tmp_path / "sales.db"))
    await s.initialize()
    return s


class TestFunnelMetrics:
    @pytest.mark.asyncio
    async def test_empty_tenant_returns_zeros(self, tmp_path: Path):
        s = await _new_store(tmp_path)
        metrics = await funnel_metrics(s, tenant="atx_mats")
        assert metrics["total_contacts"] == 0
        assert metrics["total_won"] == 0
        assert len(metrics["stages"]) == 8  # all stages present
        await s.close()

    @pytest.mark.asyncio
    async def test_contacts_default_to_cold_stage(self, tmp_path: Path):
        s = await _new_store(tmp_path)
        for i in range(5):
            await s.upsert_contact(Contact(
                tenant="atx_mats", email=f"c{i}@a.com",
                source=ContactSource.MANUAL,
            ))
        metrics = await funnel_metrics(s, tenant="atx_mats")
        cold = next(stg for stg in metrics["stages"] if stg["stage"] == "cold")
        assert cold["count"] == 5
        await s.close()

    @pytest.mark.asyncio
    async def test_opportunity_stage_counted(self, tmp_path: Path):
        s = await _new_store(tmp_path)
        cid = await s.upsert_contact(Contact(
            tenant="atx_mats", email="c@a.com",
        ))
        # Opportunities table requires datetime ISO strings — update_at will be
        # auto-assigned. Use the store interface if available; otherwise raw SQL.
        db = await s._conn()
        from datetime import datetime
        now = datetime.utcnow().isoformat()
        await db.execute(
            """INSERT INTO opportunities (tenant, contact_id, stage, created_at, updated_at)
               VALUES (?,?,?,?,?)""",
            ("atx_mats", cid, OpportunityStage.MQL.value, now, now),
        )
        await db.commit()

        metrics = await funnel_metrics(s, tenant="atx_mats")
        mql = next(stg for stg in metrics["stages"] if stg["stage"] == "mql")
        assert mql["count"] == 1
        await s.close()


class TestChannelMetrics:
    @pytest.mark.asyncio
    async def test_email_send_reply_rates(self, tmp_path: Path):
        s = await _new_store(tmp_path)
        cid = await s.upsert_contact(Contact(
            tenant="atx_mats", email="c@a.com",
        ))
        # 10 sent, 3 opened, 1 replied
        for _ in range(10):
            await s.log_activity(Activity(
                tenant="atx_mats", contact_id=cid,
                type=ActivityType.EMAIL_SENT, channel="email",
            ))
        for _ in range(3):
            await s.log_activity(Activity(
                tenant="atx_mats", contact_id=cid,
                type=ActivityType.EMAIL_OPENED, channel="email",
            ))
        await s.log_activity(Activity(
            tenant="atx_mats", contact_id=cid,
            type=ActivityType.EMAIL_REPLIED, channel="email",
        ))

        metrics = await channel_metrics(s, tenant="atx_mats")
        email = next(c for c in metrics["channels"] if c["channel"] == "email")
        assert email["sent"] == 10
        assert email["opened"] == 3
        assert email["replied"] == 1
        assert email["open_rate_pct"] == 30.0
        assert email["reply_rate_pct"] == 10.0
        await s.close()


class TestSequenceMetrics:
    @pytest.mark.asyncio
    async def test_sequence_enrollment_counts(self, tmp_path: Path):
        s = await _new_store(tmp_path)
        # Ensure atx_distributor sequence is registered
        from sovereign_swarm.sales_ops.sequences import atx_distributor  # noqa: F401

        seq = Sequencer(s)
        for i in range(3):
            c = Contact(
                tenant="atx_mats", email=f"e{i}@a.com",
                first_name=f"p{i}",
            )
            cid = await s.upsert_contact(c)
            await seq.enroll("atx_mats", cid, "atx_distributor")

        metrics = await sequence_metrics(s, tenant="atx_mats")
        seq_row = next(x for x in metrics["sequences"] if x["sequence_name"] == "atx_distributor")
        assert seq_row["enrolled"] == 3
        assert seq_row["active"] == 3
        await s.close()
