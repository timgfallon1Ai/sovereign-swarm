"""Approval workflow for outbound messages."""

from __future__ import annotations

import structlog

from sovereign_swarm.communication.models import Channel, MessageStatus, OutboundMessage

logger = structlog.get_logger()

_FINANCIAL_KEYWORDS = ["trade", "position", "order", "payment", "invoice", "transfer", "wire"]


class ApprovalManager:
    """Manages approval workflow for outbound messages.

    Rules:
    - Client-facing emails always require approval
    - Internal alerts/notifications auto-approved
    - Financial communications always require approval
    - SMS to unknown numbers requires approval
    """

    def __init__(self) -> None:
        self._pending: dict[str, OutboundMessage] = {}

    def requires_approval(self, message: OutboundMessage) -> bool:
        """Determine if a message needs human approval before sending."""
        # Auto-approve internal alerts / monitoring
        if message.metadata.get("internal", False):
            return False

        # Always approve client-facing
        if message.metadata.get("client_facing", False):
            return True

        # Always approve financial content
        body_lower = (message.body or "").lower()
        subject_lower = (message.subject or "").lower()
        combined = body_lower + " " + subject_lower
        if any(kw in combined for kw in _FINANCIAL_KEYWORDS):
            return True

        # Auto-approve system push notifications
        if message.channel == Channel.PUSH_NOTIFICATION:
            return False

        # Default: require approval for email and SMS to external recipients
        if message.channel in (Channel.EMAIL, Channel.SMS):
            return True

        return False

    async def submit_for_approval(self, message: OutboundMessage) -> str:
        """Submit a message for approval. Returns message ID."""
        message.status = MessageStatus.PENDING_APPROVAL
        self._pending[message.id] = message
        logger.info("approval.submitted", message_id=message.id, channel=message.channel)
        return message.id

    async def approve(self, message_id: str, approved_by: str = "tim") -> OutboundMessage | None:
        """Approve a pending message."""
        message = self._pending.pop(message_id, None)
        if message:
            message.status = MessageStatus.APPROVED
            message.approved_by = approved_by
            logger.info("approval.approved", message_id=message_id, by=approved_by)
        else:
            logger.warning("approval.not_found", message_id=message_id)
        return message

    async def reject(self, message_id: str) -> OutboundMessage | None:
        """Reject / cancel a pending message."""
        message = self._pending.pop(message_id, None)
        if message:
            message.status = MessageStatus.CANCELLED
            logger.info("approval.rejected", message_id=message_id)
        else:
            logger.warning("approval.not_found", message_id=message_id)
        return message

    async def get_pending(self) -> list[OutboundMessage]:
        """Return all messages awaiting approval."""
        return list(self._pending.values())
