"""Match an inbound email to existing Contact + active SequenceEnrollment.

Uses two lookup paths:
1. By sender email → Contact (primary)
2. By In-Reply-To / References headers → prior ScheduledMessage → Contact + Enrollment
"""

from __future__ import annotations

import structlog

from sovereign_swarm.inbound.sendgrid_parser import InboundEmail
from sovereign_swarm.sales_ops.models import (
    Contact,
    EnrollmentStatus,
    SequenceEnrollment,
)
from sovereign_swarm.sales_ops.store import SalesOpsStore

logger = structlog.get_logger()


class InboundMatch:
    """Result of matching an inbound email."""

    def __init__(
        self,
        contact: Contact | None = None,
        active_enrollments: list[SequenceEnrollment] | None = None,
        matched_via: str = "unmatched",
    ) -> None:
        self.contact = contact
        self.active_enrollments = active_enrollments or []
        self.matched_via = matched_via  # "email", "thread", "unmatched"

    @property
    def has_match(self) -> bool:
        return self.contact is not None


async def match_inbound(
    inbound: InboundEmail,
    tenant: str,
    sales_store: SalesOpsStore,
) -> InboundMatch:
    """Match an InboundEmail to an existing Contact for this tenant.

    Strategy:
    1. Look up Contact by sender email
    2. If found, find active enrollments for that contact
    3. Return InboundMatch with contact + enrollments

    We don't match by thread headers in v1 — email match is sufficient.
    """
    if not inbound.from_email:
        return InboundMatch(matched_via="unmatched")

    # Lookup by email — uses sales_ops list_contacts then filter
    contacts = await sales_store.list_contacts(tenant, limit=5000)
    matched_contact = None
    for c in contacts:
        if c.email.lower() == inbound.from_email.lower():
            matched_contact = c
            break

    if matched_contact is None:
        logger.info(
            "inbound.no_contact_match",
            tenant=tenant,
            from_email=inbound.from_email,
        )
        return InboundMatch(matched_via="unmatched")

    # Find active enrollments for this contact
    enrollments = await sales_store.list_enrollments(
        tenant, status=EnrollmentStatus.ACTIVE, limit=1000
    )
    active_for_contact = [
        e for e in enrollments if e.contact_id == matched_contact.id
    ]

    logger.info(
        "inbound.contact_matched",
        tenant=tenant,
        contact_id=matched_contact.id,
        active_enrollments=len(active_for_contact),
    )
    return InboundMatch(
        contact=matched_contact,
        active_enrollments=active_for_contact,
        matched_via="email",
    )
