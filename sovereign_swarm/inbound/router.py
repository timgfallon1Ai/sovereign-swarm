"""Route inbound emails to the right handler.

Decision tree:
1. Matched contact + active enrollments → pause sequences, log Activity, create Case (open status, linked to contact)
2. Matched contact + no active enrollments → create Case (linked to contact)
3. No contact match → create Case (unknown_sender tag)

In all cases a Case is created so the UI surfaces the message. The
"pause on reply" behavior handles sequence advancement.
"""

from __future__ import annotations

import structlog

from sovereign_swarm.inbound.matcher import InboundMatch, match_inbound
from sovereign_swarm.inbound.sendgrid_parser import InboundEmail
from sovereign_swarm.sales_ops.models import (
    Activity,
    ActivityType,
    EnrollmentStatus,
)
from sovereign_swarm.sales_ops.store import SalesOpsStore
from sovereign_swarm.support.models import Case, CaseMessageDirection, CaseStatus
from sovereign_swarm.support.service import CaseService
from sovereign_swarm.support.store import SupportStore

logger = structlog.get_logger()


class InboundRouter:
    """Decide what to do with an inbound email."""

    def __init__(
        self,
        sales_store: SalesOpsStore,
        support_store: SupportStore,
    ) -> None:
        self.sales_store = sales_store
        self.support_store = support_store
        self.case_service = CaseService(support_store)

    async def handle(self, inbound: InboundEmail, tenant: str) -> dict:
        """Process an inbound email. Returns a summary dict."""
        # Step 1: match
        match = await match_inbound(inbound, tenant, self.sales_store)

        # Step 2: pause active enrollments if any
        paused_count = 0
        for enrollment in match.active_enrollments:
            enrollment.status = EnrollmentStatus.PAUSED
            enrollment.exit_reason = "reply_received"
            await self.sales_store.update_enrollment(enrollment)
            paused_count += 1

        # Step 3: log Activity if matched to contact
        activity_id = None
        if match.contact and match.contact.id:
            activity = Activity(
                tenant=tenant,
                contact_id=match.contact.id,
                type=ActivityType.EMAIL_REPLIED,
                channel="email",
                subject=inbound.subject,
                body=inbound.text_body[:2000],
                outcome="inbound_reply_received",
                metadata={
                    "from_email": inbound.from_email,
                    "message_id": inbound.message_id,
                    "paused_enrollments": paused_count,
                    "attachments_count": inbound.attachments_count,
                },
            )
            activity_id = await self.sales_store.log_activity(activity)

        # Step 4: create Case for this inbound
        case = await self.case_service.create_from_inbound_email(
            tenant=tenant,
            sender=inbound.from_email or "unknown@sender",
            subject=inbound.subject,
            body=inbound.text_body,
            contact_id=match.contact.id if match.contact else None,
            metadata={
                "from_name": inbound.from_name,
                "message_id": inbound.message_id,
                "in_reply_to": inbound.in_reply_to,
                "matched_via": match.matched_via,
                "paused_enrollments": paused_count,
                "activity_id": activity_id,
            },
        )
        # If matched to active enrollment, this is a "reply" — mark case OPEN immediately
        if match.active_enrollments:
            case.status = CaseStatus.OPEN
            await self.support_store.update_case(case)

        result = {
            "case_id": case.id,
            "contact_id": match.contact.id if match.contact else None,
            "matched": match.has_match,
            "matched_via": match.matched_via,
            "paused_enrollments": paused_count,
            "activity_id": activity_id,
        }
        logger.info("inbound.routed", tenant=tenant, **result)
        return result
