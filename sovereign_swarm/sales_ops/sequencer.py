"""Sequencer — drives enrollments through their steps.

Responsibilities:
1. `enroll(contact_id, sequence_name)` — create enrollment, schedule step 0
2. `tick()` — find due enrollments, render next step's message into `scheduled_messages` (status=drafted)
3. `pause_on_reply(contact_id)` — halt sequence when a reply comes in

The sequencer NEVER sends directly — all sending goes through the
approval_queue so Tim can review messages before they leave the server.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import structlog

from sovereign_swarm.sales_ops.models import (
    Activity,
    ActivityType,
    EnrollmentStatus,
    MessageStatus,
    ScheduledMessage,
    SequenceEnrollment,
)
from sovereign_swarm.sales_ops.sequences import (
    SequenceStep,
    SequenceTemplate,
    get_sequence,
    render_template,
)
from sovereign_swarm.sales_ops.store import SalesOpsStore

logger = structlog.get_logger()


class Sequencer:
    """Drives SequenceEnrollment through its steps, staging messages for approval."""

    def __init__(self, store: SalesOpsStore) -> None:
        self.store = store

    async def enroll(
        self,
        tenant: str,
        contact_id: int,
        sequence_name: str,
    ) -> SequenceEnrollment | None:
        """Enroll a contact in a sequence. Returns the enrollment."""
        tmpl = get_sequence(sequence_name)
        if tmpl is None:
            logger.warning("sequencer.unknown_sequence", name=sequence_name)
            return None

        contact = await self.store.get_contact(contact_id)
        if contact is None:
            logger.warning("sequencer.unknown_contact", contact_id=contact_id)
            return None
        if contact.tenant != tenant:
            logger.warning(
                "sequencer.tenant_mismatch",
                contact_tenant=contact.tenant,
                expected=tenant,
            )
            return None
        if contact.unsubscribed:
            logger.info("sequencer.skip_unsubscribed", contact_id=contact_id)
            return None

        enrollment = SequenceEnrollment(
            tenant=tenant,
            contact_id=contact_id,
            sequence_name=sequence_name,
            current_step=0,
            status=EnrollmentStatus.ACTIVE,
            next_action_at=datetime.utcnow(),  # immediately due
        )
        enrollment.id = await self.store.create_enrollment(enrollment)
        logger.info(
            "sequencer.enrolled",
            enrollment_id=enrollment.id,
            contact_id=contact_id,
            sequence=sequence_name,
        )
        return enrollment

    async def tick(self, tenant: str | None = None) -> list[ScheduledMessage]:
        """Find due enrollments, render next step, stage messages as drafted.

        Returns the list of messages created in this tick.
        """
        due = await self.store.due_enrollments(tenant=tenant)
        created: list[ScheduledMessage] = []

        for enrollment in due:
            msgs = await self._process_enrollment(enrollment)
            created.extend(msgs)

        if created:
            logger.info("sequencer.tick_complete", drafted=len(created))
        return created

    async def _process_enrollment(
        self, enrollment: SequenceEnrollment
    ) -> list[ScheduledMessage]:
        """Render the current step into a drafted message, advance enrollment."""
        tmpl = get_sequence(enrollment.sequence_name)
        if tmpl is None:
            enrollment.status = EnrollmentStatus.EXITED
            enrollment.exit_reason = "sequence_not_found"
            enrollment.completed_at = datetime.utcnow()
            await self.store.update_enrollment(enrollment)
            return []

        step = tmpl.get_step(enrollment.current_step)
        if step is None:
            # Sequence complete
            enrollment.status = EnrollmentStatus.COMPLETED
            enrollment.completed_at = datetime.utcnow()
            enrollment.next_action_at = None
            await self.store.update_enrollment(enrollment)
            logger.info("sequencer.completed", enrollment_id=enrollment.id)
            return []

        contact = await self.store.get_contact(enrollment.contact_id)
        if contact is None or contact.unsubscribed:
            enrollment.status = EnrollmentStatus.EXITED
            enrollment.exit_reason = "contact_missing_or_unsubscribed"
            enrollment.completed_at = datetime.utcnow()
            await self.store.update_enrollment(enrollment)
            return []

        brand = self._load_brand(enrollment.tenant)

        # Hydrate company name for template rendering
        if contact.company_id is not None:
            company = await self.store.get_company(contact.company_id)
            if company:
                contact._company_name = company.name  # type: ignore

        messages = await self._render_step(step, enrollment, contact, brand)

        # Advance enrollment to next step
        next_step = tmpl.get_step(enrollment.current_step + 1)
        if next_step is None:
            enrollment.next_action_at = None
        else:
            delay_days = max(next_step.day_offset - step.day_offset, 1)
            enrollment.next_action_at = datetime.utcnow() + timedelta(days=delay_days)
        enrollment.current_step += 1
        await self.store.update_enrollment(enrollment)

        return messages

    async def _render_step(
        self,
        step: SequenceStep,
        enrollment: SequenceEnrollment,
        contact: Any,
        brand: Any,
    ) -> list[ScheduledMessage]:
        """Render a step into a ScheduledMessage (drafted)."""
        subject = render_template(step.subject_template, contact, brand)
        body = render_template(step.body_template, contact, brand)

        # content_generator lets the step run an LLM for dynamic content
        if step.content_generator is not None:
            try:
                maybe = step.content_generator(contact=contact, brand=brand, step=step)
                if hasattr(maybe, "__await__"):
                    generated = await maybe  # type: ignore
                else:
                    generated = maybe
                if isinstance(generated, tuple) and len(generated) == 2:
                    subject, body = generated
                elif isinstance(generated, dict):
                    subject = generated.get("subject", subject)
                    body = generated.get("body", body)
            except Exception as exc:
                logger.warning(
                    "sequencer.content_generator_failed",
                    step_index=step.index,
                    error=str(exc),
                )

        msg = ScheduledMessage(
            tenant=enrollment.tenant,
            enrollment_id=enrollment.id or 0,
            contact_id=contact.id or 0,
            step_index=step.index,
            channel=step.channel,
            subject=subject,
            body=body,
            status=MessageStatus.DRAFTED,
            scheduled_for=datetime.utcnow(),
        )
        msg.id = await self.store.create_message(msg)
        logger.info(
            "sequencer.drafted",
            message_id=msg.id,
            step=step.index,
            channel=step.channel.value,
            manual_only=step.manual_only,
        )
        return [msg]

    async def pause_on_reply(self, contact_id: int, reason: str = "reply_received") -> int:
        """Pause all active enrollments for a contact who replied. Returns count paused."""
        enrollments = await self.store.list_enrollments(
            tenant="",  # hack — we filter by contact below
            limit=1000,
        )
        # The list API filters by tenant; we need all. Pull directly.
        # For pilot, tolerate the tenant-scoped call by iterating through known tenants.
        count = 0
        contact = await self.store.get_contact(contact_id)
        if contact is None:
            return 0
        enrollments = await self.store.list_enrollments(
            tenant=contact.tenant, status=EnrollmentStatus.ACTIVE
        )
        for e in enrollments:
            if e.contact_id != contact_id:
                continue
            e.status = EnrollmentStatus.PAUSED
            e.exit_reason = reason
            await self.store.update_enrollment(e)
            count += 1

        # Log the reply activity
        activity = Activity(
            tenant=contact.tenant,
            contact_id=contact_id,
            type=ActivityType.EMAIL_REPLIED,
            outcome="sequences_paused_for_human_review",
            metadata={"paused_count": count, "reason": reason},
        )
        await self.store.log_activity(activity)
        logger.info("sequencer.paused_on_reply", contact_id=contact_id, count=count)
        return count

    @staticmethod
    def _load_brand(tenant: str) -> Any:
        try:
            from sovereign_swarm.marketing.brand import get_brand
            return get_brand(tenant)
        except Exception:
            return None
