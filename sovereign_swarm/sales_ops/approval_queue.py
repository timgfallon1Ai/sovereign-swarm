"""Approval queue — the human-in-the-loop gate before any message goes out.

Every message that the sequencer stages lands here as `drafted`. Tim
reviews via CLI (`sales queue`), then either:
- `approve <id>` → sends via communication channel → status=sent
- `skip <id> <reason>` → mark as skipped, don't send
- `approve --all-safe` → bulk approve steps 1-3 (low-risk intros only),
  never auto-approves steps with `requires_explicit_approval=True`.

The queue calls existing `communication/channels/*` for sending.
Manual-only steps (calls, LinkedIn, reminders) are NEVER auto-sent —
they're shown to Tim as tasks to do offline.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import structlog

from sovereign_swarm.sales_ops.models import (
    Activity,
    ActivityType,
    MessageChannel,
    MessageStatus,
    ScheduledMessage,
)
from sovereign_swarm.sales_ops.sequences import get_sequence
from sovereign_swarm.sales_ops.store import SalesOpsStore

logger = structlog.get_logger()


class ApprovalQueue:
    """Human-in-the-loop message approval + send dispatch."""

    def __init__(self, store: SalesOpsStore) -> None:
        self.store = store
        self._email_channel = None
        self._sms_channel = None

    async def pending(self, tenant: str | None = None) -> list[ScheduledMessage]:
        """List all drafted messages awaiting approval."""
        return await self.store.pending_messages(
            tenant=tenant, status=MessageStatus.DRAFTED
        )

    async def approve(self, message_id: int) -> bool:
        """Mark a message approved + send. Returns True on success."""
        msg = await self.store.get_message(message_id)
        if msg is None:
            logger.warning("approval_queue.not_found", message_id=message_id)
            return False
        if msg.status != MessageStatus.DRAFTED:
            logger.warning(
                "approval_queue.wrong_status",
                message_id=message_id,
                status=msg.status.value,
            )
            return False
        msg.approved_at = datetime.utcnow()
        msg.status = MessageStatus.APPROVED
        await self.store.update_message(msg)
        return await self._send(msg)

    async def approve_all_safe(self, tenant: str | None = None) -> dict[str, int]:
        """Approve and send all low-risk messages.

        Low-risk = step belongs to a sequence step that does NOT have
        `requires_explicit_approval=True` AND is not `manual_only`.
        Steps 1-3 of most B2B sequences qualify; ROI, pricing, and SMS
        steps do NOT.
        """
        sent = skipped_unsafe = failed = 0
        for msg in await self.pending(tenant=tenant):
            step = self._get_step(msg)
            if step is None:
                skipped_unsafe += 1
                continue
            if step.requires_explicit_approval or step.manual_only:
                skipped_unsafe += 1
                continue
            ok = await self.approve(msg.id or 0)
            if ok:
                sent += 1
            else:
                failed += 1
        return {"sent": sent, "skipped_unsafe": skipped_unsafe, "failed": failed}

    async def skip(self, message_id: int, reason: str = "") -> bool:
        """Mark a message as skipped (will not send)."""
        msg = await self.store.get_message(message_id)
        if msg is None:
            return False
        msg.status = MessageStatus.SKIPPED
        msg.error = reason
        await self.store.update_message(msg)
        logger.info("approval_queue.skipped", message_id=message_id, reason=reason)
        return True

    async def mark_manual_complete(self, message_id: int, outcome: str = "") -> bool:
        """For manual-only steps — mark as sent after Tim does the offline action."""
        msg = await self.store.get_message(message_id)
        if msg is None:
            return False
        step = self._get_step(msg)
        if step is None or not step.manual_only:
            logger.warning("approval_queue.not_manual_step", message_id=message_id)
            return False
        msg.status = MessageStatus.SENT
        msg.sent_at = datetime.utcnow()
        msg.error = ""
        await self.store.update_message(msg)

        activity = Activity(
            tenant=msg.tenant,
            contact_id=msg.contact_id,
            type=self._channel_to_activity(msg.channel),
            channel=msg.channel.value,
            subject=msg.subject,
            body=msg.body,
            outcome=outcome or "manual_action_complete",
        )
        await self.store.log_activity(activity)
        return True

    async def _send(self, msg: ScheduledMessage) -> bool:
        """Dispatch to the right channel. Manual-only steps are not sent."""
        step = self._get_step(msg)
        if step is not None and step.manual_only:
            # Manual steps don't actually send — they wait for Tim to
            # mark them complete via `mark_manual_complete`.
            msg.status = MessageStatus.APPROVED  # stays in queue as 'approved, awaiting manual action'
            await self.store.update_message(msg)
            return True

        try:
            ok = False
            if msg.channel == MessageChannel.EMAIL:
                ok = await self._send_email(msg)
            elif msg.channel == MessageChannel.SMS:
                ok = await self._send_sms(msg)
            else:
                # LinkedIn, call, manual — no API, treat as manual
                ok = True

            msg.status = MessageStatus.SENT if ok else MessageStatus.FAILED
            if ok:
                msg.sent_at = datetime.utcnow()
            await self.store.update_message(msg)

            if ok:
                activity = Activity(
                    tenant=msg.tenant,
                    contact_id=msg.contact_id,
                    type=self._channel_to_activity(msg.channel),
                    channel=msg.channel.value,
                    subject=msg.subject,
                    body=msg.body,
                    outcome="sent",
                    metadata={"message_id": msg.id},
                )
                await self.store.log_activity(activity)
            return ok
        except Exception as exc:
            msg.status = MessageStatus.FAILED
            msg.error = str(exc)
            await self.store.update_message(msg)
            logger.error("approval_queue.send_failed", message_id=msg.id, error=str(exc))
            return False

    async def _send_email(self, msg: ScheduledMessage) -> bool:
        channel = self._get_email_channel()
        if channel is None:
            logger.error("approval_queue.no_email_channel")
            return False
        contact = await self.store.get_contact(msg.contact_id)
        if contact is None or not contact.email:
            logger.warning("approval_queue.no_email_address", contact_id=msg.contact_id)
            return False

        from sovereign_swarm.communication.models import (
            Channel as CommChannel,
            OutboundMessage,
        )
        outbound = OutboundMessage(
            channel=CommChannel.EMAIL,
            to=[contact.email],
            subject=msg.subject,
            body=msg.body,
        )
        return await channel.send(outbound)

    async def _send_sms(self, msg: ScheduledMessage) -> bool:
        contact = await self.store.get_contact(msg.contact_id)
        if contact is None or not contact.phone:
            logger.warning("approval_queue.no_phone", contact_id=msg.contact_id)
            return False
        if not contact.consent_sms:
            logger.warning("approval_queue.no_sms_consent", contact_id=msg.contact_id)
            return False
        channel = self._get_sms_channel()
        if channel is None:
            logger.error("approval_queue.no_sms_channel")
            return False

        from sovereign_swarm.communication.models import (
            Channel as CommChannel,
            OutboundMessage,
        )
        outbound = OutboundMessage(
            channel=CommChannel.SMS,
            to=[contact.phone],
            body=msg.body,
        )
        return await channel.send(outbound)

    def _get_email_channel(self):
        if self._email_channel is None:
            try:
                from sovereign_swarm.communication.channels.email import EmailChannel
                self._email_channel = EmailChannel()
            except Exception as exc:
                logger.error("approval_queue.email_import_failed", error=str(exc))
                self._email_channel = False
        return self._email_channel if self._email_channel is not False else None

    def _get_sms_channel(self):
        if self._sms_channel is None:
            try:
                from sovereign_swarm.communication.channels.sms import SMSChannel
                self._sms_channel = SMSChannel()
            except Exception as exc:
                logger.error("approval_queue.sms_import_failed", error=str(exc))
                self._sms_channel = False
        return self._sms_channel if self._sms_channel is not False else None

    @staticmethod
    def _get_step(msg: ScheduledMessage):
        """Look up the step definition for a message."""
        # We don't know the sequence name from the message alone; resolve via enrollment.
        # For perf in pilot, keep it simple and scan atx_distributor since it's the only
        # sequence today. Revisit when we have 3+ sequences.
        from sovereign_swarm.sales_ops.sequences import list_sequences
        for tmpl in list_sequences():
            if 0 <= msg.step_index < tmpl.length:
                return tmpl.steps[msg.step_index]
        return None

    @staticmethod
    def _channel_to_activity(channel: MessageChannel) -> ActivityType:
        mapping = {
            MessageChannel.EMAIL: ActivityType.EMAIL_SENT,
            MessageChannel.SMS: ActivityType.SMS_SENT,
            MessageChannel.LINKEDIN: ActivityType.LINKEDIN_MESSAGE,
            MessageChannel.CALL: ActivityType.CALL_ATTEMPTED,
            MessageChannel.MANUAL: ActivityType.NOTE,
        }
        return mapping.get(channel, ActivityType.NOTE)
