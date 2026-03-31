"""Slack channel — sends via webhook URL or Bot Token API."""

from __future__ import annotations

import os
from typing import Any

import structlog

from sovereign_swarm.communication.models import OutboundMessage

logger = structlog.get_logger()


class SlackChannel:
    """Send messages to Slack via webhook or Bot API."""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        config = config or {}
        self._webhook_url = config.get("slack_webhook_url") or os.getenv("SLACK_WEBHOOK_URL", "")
        self._bot_token = config.get("slack_bot_token") or os.getenv("SLACK_BOT_TOKEN", "")

    async def send(self, message: OutboundMessage) -> bool:
        """Send a Slack message. Uses bot API if recipients look like channels/users, else webhook."""
        if self._bot_token and message.to:
            return await self._send_bot_api(message)
        if self._webhook_url:
            return await self._send_webhook(message)
        logger.error("slack.no_provider", msg="No SLACK_WEBHOOK_URL or SLACK_BOT_TOKEN configured")
        return False

    async def send_to_channel(self, channel: str, text: str) -> bool:
        """Convenience: send a plain text message to a specific Slack channel."""
        if self._bot_token:
            return await self._post_chat(channel, text)
        if self._webhook_url:
            return await self._send_webhook_text(text)
        logger.error("slack.no_provider")
        return False

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _send_bot_api(self, message: OutboundMessage) -> bool:
        try:
            import httpx

            all_ok = True
            text = self._format_message(message)

            async with httpx.AsyncClient() as client:
                for target in message.to:
                    ok = await self._post_chat(target, text, client=client)
                    if not ok:
                        all_ok = False
            return all_ok
        except Exception as exc:
            logger.error("slack.bot_error", error=str(exc))
            return False

    async def _post_chat(self, channel: str, text: str, client: Any | None = None) -> bool:
        import httpx

        close_after = client is None
        client = client or httpx.AsyncClient()
        try:
            resp = await client.post(
                "https://slack.com/api/chat.postMessage",
                json={"channel": channel, "text": text},
                headers={"Authorization": f"Bearer {self._bot_token}"},
            )
            data = resp.json()
            if data.get("ok"):
                logger.info("slack.sent", channel=channel)
                return True
            logger.error("slack.api_error", channel=channel, error=data.get("error"))
            return False
        finally:
            if close_after:
                await client.aclose()

    async def _send_webhook(self, message: OutboundMessage) -> bool:
        return await self._send_webhook_text(self._format_message(message))

    async def _send_webhook_text(self, text: str) -> bool:
        try:
            import httpx

            async with httpx.AsyncClient() as client:
                resp = await client.post(self._webhook_url, json={"text": text})
            if resp.status_code == 200:
                logger.info("slack.webhook_sent")
                return True
            logger.error("slack.webhook_failed", status=resp.status_code)
            return False
        except Exception as exc:
            logger.error("slack.webhook_error", error=str(exc))
            return False

    @staticmethod
    def _format_message(message: OutboundMessage) -> str:
        parts: list[str] = []
        if message.subject:
            parts.append(f"*{message.subject}*")
        if message.body:
            parts.append(message.body)
        return "\n".join(parts) if parts else "(empty message)"
