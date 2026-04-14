"""Tests for the inbound module (SendGrid parser + router)."""

from __future__ import annotations

from pathlib import Path

import pytest

from sovereign_swarm.inbound.router import InboundRouter
from sovereign_swarm.inbound.sendgrid_parser import parse_sendgrid_webhook
from sovereign_swarm.sales_ops.models import (
    Contact,
    ContactSource,
    EnrollmentStatus,
)
from sovereign_swarm.sales_ops.sequencer import Sequencer
from sovereign_swarm.sales_ops.store import SalesOpsStore
from sovereign_swarm.support.store import SupportStore


class TestSendGridParser:
    def test_parse_basic_payload(self):
        payload = {
            "from": 'Jane Doe <jane@acme.com>',
            "to": "tim@atxmats.com",
            "subject": "Re: Quote for 20k sqft",
            "text": "Thanks, can you call next week?",
            "headers": "Message-ID: <abc123@acme.com>\nIn-Reply-To: <prev456@atxmats.com>\n",
        }
        inbound = parse_sendgrid_webhook(payload)
        assert inbound.from_email == "jane@acme.com"
        assert inbound.from_name == "Jane Doe"
        assert "tim@atxmats.com" in inbound.to_emails
        assert inbound.subject == "Re: Quote for 20k sqft"
        assert inbound.text_body == "Thanks, can you call next week?"
        assert inbound.message_id == "<abc123@acme.com>"
        assert inbound.in_reply_to == "<prev456@atxmats.com>"

    def test_parse_minimal_payload(self):
        payload = {
            "from": "plain@sender.com",
            "to": "us@atx.com",
            "subject": "",
            "text": "",
        }
        inbound = parse_sendgrid_webhook(payload)
        assert inbound.from_email == "plain@sender.com"
        assert inbound.from_name == ""

    def test_parse_handles_no_headers(self):
        payload = {"from": "a@b.c", "to": "x@y.z", "subject": "s", "text": "t"}
        inbound = parse_sendgrid_webhook(payload)
        assert inbound.message_id == ""
        assert inbound.in_reply_to == ""
        assert inbound.references == []


class TestInboundRouter:
    @pytest.mark.asyncio
    async def test_route_unknown_sender_creates_unmatched_case(self, tmp_path: Path):
        sales = SalesOpsStore(db_path=str(tmp_path / "sales.db"))
        support = SupportStore(db_path=str(tmp_path / "support.db"))
        await sales.initialize()
        await support.initialize()
        router = InboundRouter(sales, support)

        payload = {
            "from": "stranger@nowhere.com",
            "to": "info@atxmats.com",
            "subject": "Cold inquiry",
            "text": "Are you a distributor?",
        }
        inbound = parse_sendgrid_webhook(payload)
        result = await router.handle(inbound, tenant="atx_mats")
        assert result["matched"] is False
        assert result["matched_via"] == "unmatched"
        assert result["paused_enrollments"] == 0
        assert result["case_id"] is not None

    @pytest.mark.asyncio
    async def test_route_known_sender_pauses_active_enrollment(self, tmp_path: Path):
        sales = SalesOpsStore(db_path=str(tmp_path / "sales.db"))
        support = SupportStore(db_path=str(tmp_path / "support.db"))
        await sales.initialize()
        await support.initialize()

        # Seed a contact + enrollment
        contact = Contact(
            tenant="atx_mats", email="jane@acme.com",
            first_name="Jane", last_name="Doe",
            source=ContactSource.APOLLO,
        )
        cid = await sales.upsert_contact(contact)

        seq = Sequencer(sales)
        enrollment = await seq.enroll("atx_mats", cid, "atx_distributor")
        assert enrollment is not None

        router = InboundRouter(sales, support)
        payload = {
            "from": 'Jane Doe <jane@acme.com>',
            "to": "info@atxmats.com",
            "subject": "Re: ATX outreach",
            "text": "Interested — call me",
        }
        inbound = parse_sendgrid_webhook(payload)
        result = await router.handle(inbound, tenant="atx_mats")

        assert result["matched"] is True
        assert result["matched_via"] == "email"
        assert result["paused_enrollments"] == 1
        assert result["case_id"] is not None

        # Verify enrollment paused
        e = await sales.get_enrollment(enrollment.id)
        assert e.status == EnrollmentStatus.PAUSED
        assert e.exit_reason == "reply_received"

        # Verify case created with contact_id linked
        case = await support.get_case(result["case_id"])
        assert case.contact_id == cid

        await sales.close()
        await support.close()

    @pytest.mark.asyncio
    async def test_route_known_sender_no_active_enrollment(self, tmp_path: Path):
        sales = SalesOpsStore(db_path=str(tmp_path / "sales.db"))
        support = SupportStore(db_path=str(tmp_path / "support.db"))
        await sales.initialize()
        await support.initialize()

        contact = Contact(
            tenant="atx_mats", email="warranty@acme.com",
            first_name="Acme", last_name="Buyer",
        )
        cid = await sales.upsert_contact(contact)

        router = InboundRouter(sales, support)
        payload = {
            "from": "warranty@acme.com",
            "to": "info@atxmats.com",
            "subject": "Warranty claim",
            "text": "Mat failed after 6 months.",
        }
        inbound = parse_sendgrid_webhook(payload)
        result = await router.handle(inbound, tenant="atx_mats")

        assert result["matched"] is True
        assert result["paused_enrollments"] == 0  # no active enrollments
        assert result["case_id"] is not None

        await sales.close()
        await support.close()
