"""CommunicationAgent — unified outbox for sending messages across channels."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import structlog

from sovereign_swarm.communication.approval import ApprovalManager
from sovereign_swarm.communication.channels.email import EmailChannel
from sovereign_swarm.communication.channels.push import PushChannel
from sovereign_swarm.communication.channels.slack import SlackChannel
from sovereign_swarm.communication.channels.sms import SMSChannel
from sovereign_swarm.communication.models import (
    Channel,
    MessagePriority,
    MessageStatus,
    OutboundMessage,
)
from sovereign_swarm.communication.template_engine import TemplateEngine
from sovereign_swarm.protocol.swarm_agent import (
    SwarmAgent,
    SwarmAgentCard,
    SwarmAgentRequest,
    SwarmAgentResponse,
)

logger = structlog.get_logger()


class CommunicationAgent(SwarmAgent):
    """Unified outbox agent for email, SMS, Slack, WhatsApp, and push notifications."""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._config = config or {}
        self._email = EmailChannel(self._config)
        self._sms = SMSChannel(self._config)
        self._slack = SlackChannel(self._config)
        self._push = PushChannel()
        self._approval = ApprovalManager()
        self._templates = TemplateEngine()
        self._sent_log: list[OutboundMessage] = []

    @property
    def card(self) -> SwarmAgentCard:
        return SwarmAgentCard(
            name="CommunicationAgent",
            description=(
                "Unified outbox for sending messages across email, SMS, Slack, "
                "and push notifications with approval workflows for client-facing comms."
            ),
            version="0.1.0",
            domains=["communication", "email", "sms", "slack", "messaging"],
            supported_intents=[
                "send_email",
                "send_sms",
                "send_slack",
                "draft_message",
                "list_pending",
                "approve_message",
            ],
            capabilities=[
                "send_email",
                "send_sms",
                "send_slack",
                "draft_message",
                "list_pending",
                "approve_message",
            ],
        )

    async def execute(self, request: SwarmAgentRequest) -> SwarmAgentResponse:
        """Route task to the appropriate communication action."""
        task = request.task.lower()
        params = request.parameters

        try:
            if any(kw in task for kw in ("pending", "queue")):
                return await self._handle_list_pending()

            if "approve" in task:
                return await self._handle_approve(params)

            if "reject" in task or "cancel" in task:
                return await self._handle_reject(params)

            if "draft" in task:
                return await self._handle_draft(params)

            if any(kw in task for kw in ("send email", "email")):
                return await self._handle_send(Channel.EMAIL, params)

            if any(kw in task for kw in ("send sms", "text", "sms")):
                return await self._handle_send(Channel.SMS, params)

            if any(kw in task for kw in ("slack", "notify")):
                return await self._handle_send(Channel.SLACK, params)

            if "push" in task:
                return await self._handle_send(Channel.PUSH_NOTIFICATION, params)

            return SwarmAgentResponse(
                agent_name=self.card.name,
                status="error",
                error=f"Could not determine action from task: {request.task}",
            )
        except Exception as exc:
            logger.error("communication.execute_error", error=str(exc))
            return SwarmAgentResponse(
                agent_name=self.card.name,
                status="error",
                error=str(exc),
            )

    # ------------------------------------------------------------------
    # Action handlers
    # ------------------------------------------------------------------

    async def _handle_send(
        self, channel: Channel, params: dict[str, Any]
    ) -> SwarmAgentResponse:
        """Build a message, check approval, and send or queue."""
        message = self._build_message(channel, params)

        # Check if template requested
        template_name = params.get("template")
        if template_name:
            try:
                variables = params.get("template_variables", {})
                subject, body = self._templates.render(template_name, variables)
                message.subject = subject
                message.body = body
            except ValueError as exc:
                return SwarmAgentResponse(
                    agent_name=self.card.name,
                    status="error",
                    error=str(exc),
                )

        # Approval check
        if self._approval.requires_approval(message):
            message.requires_approval = True
            await self._approval.submit_for_approval(message)
            return SwarmAgentResponse(
                agent_name=self.card.name,
                status="needs_approval",
                output=self._format_message_summary(message, "Queued for approval"),
                data={"message_id": message.id, "status": "pending_approval"},
            )

        # Auto-approved — send immediately
        message.status = MessageStatus.APPROVED
        success = await self._dispatch(message)

        if success:
            message.status = MessageStatus.SENT
            message.sent_at = datetime.now(timezone.utc)
            self._sent_log.append(message)
            return SwarmAgentResponse(
                agent_name=self.card.name,
                status="success",
                output=self._format_message_summary(message, "Sent"),
                data={"message_id": message.id, "status": "sent"},
            )

        message.status = MessageStatus.FAILED
        return SwarmAgentResponse(
            agent_name=self.card.name,
            status="error",
            output=self._format_message_summary(message, "Failed"),
            error="Message dispatch failed — check channel configuration.",
            data={"message_id": message.id, "status": "failed"},
        )

    async def _handle_draft(self, params: dict[str, Any]) -> SwarmAgentResponse:
        """Create a draft message without sending."""
        channel_str = params.get("channel", "email")
        channel = Channel(channel_str)
        message = self._build_message(channel, params)
        message.status = MessageStatus.DRAFT

        template_name = params.get("template")
        if template_name:
            try:
                variables = params.get("template_variables", {})
                subject, body = self._templates.render(template_name, variables)
                message.subject = subject
                message.body = body
            except ValueError as exc:
                return SwarmAgentResponse(
                    agent_name=self.card.name,
                    status="error",
                    error=str(exc),
                )

        return SwarmAgentResponse(
            agent_name=self.card.name,
            status="success",
            output=self._format_message_summary(message, "Draft created"),
            data={
                "message_id": message.id,
                "status": "draft",
                "message": message.model_dump(mode="json"),
            },
        )

    async def _handle_list_pending(self) -> SwarmAgentResponse:
        """List all messages pending approval."""
        pending = await self._approval.get_pending()
        if not pending:
            return SwarmAgentResponse(
                agent_name=self.card.name,
                status="success",
                output="No messages pending approval.",
                data={"pending_count": 0},
            )

        lines = [f"## Pending Approval ({len(pending)} messages)\n"]
        for msg in pending:
            lines.append(self._format_message_summary(msg, "Pending"))
            lines.append("---")
        return SwarmAgentResponse(
            agent_name=self.card.name,
            status="success",
            output="\n".join(lines),
            data={"pending_count": len(pending), "message_ids": [m.id for m in pending]},
        )

    async def _handle_approve(self, params: dict[str, Any]) -> SwarmAgentResponse:
        """Approve a pending message and send it."""
        message_id = params.get("message_id", "")
        approved_by = params.get("approved_by", "tim")

        if not message_id:
            return SwarmAgentResponse(
                agent_name=self.card.name,
                status="error",
                error="message_id is required for approval.",
            )

        message = await self._approval.approve(message_id, approved_by)
        if not message:
            return SwarmAgentResponse(
                agent_name=self.card.name,
                status="error",
                error=f"Message {message_id} not found in pending queue.",
            )

        success = await self._dispatch(message)
        if success:
            message.status = MessageStatus.SENT
            message.sent_at = datetime.now(timezone.utc)
            self._sent_log.append(message)
            return SwarmAgentResponse(
                agent_name=self.card.name,
                status="success",
                output=self._format_message_summary(message, "Approved and sent"),
                data={"message_id": message.id, "status": "sent"},
            )

        message.status = MessageStatus.FAILED
        return SwarmAgentResponse(
            agent_name=self.card.name,
            status="error",
            output=self._format_message_summary(message, "Approved but send failed"),
            error="Dispatch failed after approval.",
            data={"message_id": message.id, "status": "failed"},
        )

    async def _handle_reject(self, params: dict[str, Any]) -> SwarmAgentResponse:
        """Reject a pending message."""
        message_id = params.get("message_id", "")
        if not message_id:
            return SwarmAgentResponse(
                agent_name=self.card.name,
                status="error",
                error="message_id is required for rejection.",
            )

        message = await self._approval.reject(message_id)
        if not message:
            return SwarmAgentResponse(
                agent_name=self.card.name,
                status="error",
                error=f"Message {message_id} not found in pending queue.",
            )

        return SwarmAgentResponse(
            agent_name=self.card.name,
            status="success",
            output=self._format_message_summary(message, "Rejected"),
            data={"message_id": message.id, "status": "cancelled"},
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _build_message(self, channel: Channel, params: dict[str, Any]) -> OutboundMessage:
        """Construct an OutboundMessage from request parameters."""
        to = params.get("to", [])
        if isinstance(to, str):
            to = [to]

        cc = params.get("cc", [])
        if isinstance(cc, str):
            cc = [cc]

        priority_str = params.get("priority", "normal")
        try:
            priority = MessagePriority(priority_str)
        except ValueError:
            priority = MessagePriority.NORMAL

        return OutboundMessage(
            channel=channel,
            to=to,
            cc=cc,
            subject=params.get("subject", ""),
            body=params.get("body", ""),
            html_body=params.get("html_body", ""),
            attachments=params.get("attachments", []),
            priority=priority,
            thread_id=params.get("thread_id"),
            metadata=params.get("metadata", {}),
        )

    async def _dispatch(self, message: OutboundMessage) -> bool:
        """Send via the appropriate channel."""
        channel_map = {
            Channel.EMAIL: self._email,
            Channel.SMS: self._sms,
            Channel.SLACK: self._slack,
            Channel.PUSH_NOTIFICATION: self._push,
        }
        handler = channel_map.get(message.channel)
        if not handler:
            logger.error("communication.unsupported_channel", channel=message.channel)
            return False
        return await handler.send(message)

    @staticmethod
    def _format_message_summary(message: OutboundMessage, status_label: str) -> str:
        """Format a message into a readable markdown summary."""
        body_preview = (message.body or "")[:200]
        if len(message.body or "") > 200:
            body_preview += "..."

        lines = [
            f"### Message [{message.id}] — {status_label}",
            f"- **Channel:** {message.channel.value}",
            f"- **To:** {', '.join(message.to)}",
        ]
        if message.cc:
            lines.append(f"- **CC:** {', '.join(message.cc)}")
        if message.subject:
            lines.append(f"- **Subject:** {message.subject}")
        lines.append(f"- **Body:** {body_preview}")
        lines.append(f"- **Priority:** {message.priority.value}")
        lines.append(f"- **Status:** {message.status.value}")
        if message.approved_by:
            lines.append(f"- **Approved by:** {message.approved_by}")
        if message.sent_at:
            lines.append(f"- **Sent at:** {message.sent_at.isoformat()}")
        return "\n".join(lines)
