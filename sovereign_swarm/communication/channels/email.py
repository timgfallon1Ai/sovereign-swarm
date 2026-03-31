"""Email channel — sends via SendGrid API or SMTP fallback."""

from __future__ import annotations

import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

import structlog

from sovereign_swarm.communication.models import OutboundMessage

logger = structlog.get_logger()


class EmailChannel:
    """Send emails via SendGrid API or SMTP fallback."""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        config = config or {}
        self._sendgrid_key = config.get("sendgrid_api_key") or os.getenv("SENDGRID_API_KEY", "")
        self._smtp_host = config.get("smtp_host") or os.getenv("SMTP_HOST", "")
        self._smtp_port = int(config.get("smtp_port") or os.getenv("SMTP_PORT", "587"))
        self._smtp_user = config.get("smtp_user") or os.getenv("SMTP_USER", "")
        self._smtp_pass = config.get("smtp_pass") or os.getenv("SMTP_PASS", "")
        self._from_email = config.get("from_email") or os.getenv("FROM_EMAIL", "tim@fallon.ai")

    async def send(self, message: OutboundMessage) -> bool:
        """Send email via SendGrid API or SMTP fallback."""
        if self._sendgrid_key:
            return await self._send_sendgrid(message)
        if self._smtp_host:
            return await self._send_smtp(message)
        logger.error("email.no_provider", msg="No SendGrid key or SMTP config found")
        return False

    async def send_with_template(
        self, template_id: str, to: list[str], variables: dict[str, Any]
    ) -> bool:
        """Send email using a SendGrid dynamic template."""
        if not self._sendgrid_key:
            logger.error("email.template_requires_sendgrid")
            return False
        try:
            import httpx

            payload = {
                "personalizations": [{"to": [{"email": addr} for addr in to], "dynamic_template_data": variables}],
                "from": {"email": self._from_email},
                "template_id": template_id,
            }
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    "https://api.sendgrid.com/v3/mail/send",
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {self._sendgrid_key}",
                        "Content-Type": "application/json",
                    },
                )
            if resp.status_code in (200, 202):
                logger.info("email.template_sent", to=to, template_id=template_id)
                return True
            logger.error("email.template_failed", status=resp.status_code, body=resp.text)
            return False
        except Exception as exc:
            logger.error("email.template_error", error=str(exc))
            return False

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _send_sendgrid(self, message: OutboundMessage) -> bool:
        try:
            import httpx

            personalizations: dict[str, Any] = {"to": [{"email": addr} for addr in message.to]}
            if message.cc:
                personalizations["cc"] = [{"email": addr} for addr in message.cc]

            content = []
            if message.body:
                content.append({"type": "text/plain", "value": message.body})
            if message.html_body:
                content.append({"type": "text/html", "value": message.html_body})
            if not content:
                content.append({"type": "text/plain", "value": ""})

            payload = {
                "personalizations": [personalizations],
                "from": {"email": self._from_email},
                "subject": message.subject,
                "content": content,
            }
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    "https://api.sendgrid.com/v3/mail/send",
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {self._sendgrid_key}",
                        "Content-Type": "application/json",
                    },
                )
            if resp.status_code in (200, 202):
                logger.info("email.sent", to=message.to, subject=message.subject)
                return True
            logger.error("email.sendgrid_failed", status=resp.status_code, body=resp.text)
            return False
        except Exception as exc:
            logger.error("email.sendgrid_error", error=str(exc))
            return False

    async def _send_smtp(self, message: OutboundMessage) -> bool:
        try:
            msg = MIMEMultipart("alternative")
            msg["From"] = self._from_email
            msg["To"] = ", ".join(message.to)
            if message.cc:
                msg["Cc"] = ", ".join(message.cc)
            msg["Subject"] = message.subject

            if message.body:
                msg.attach(MIMEText(message.body, "plain"))
            if message.html_body:
                msg.attach(MIMEText(message.html_body, "html"))

            recipients = message.to + message.cc

            with smtplib.SMTP(self._smtp_host, self._smtp_port) as server:
                server.starttls()
                if self._smtp_user:
                    server.login(self._smtp_user, self._smtp_pass)
                server.sendmail(self._from_email, recipients, msg.as_string())

            logger.info("email.smtp_sent", to=message.to, subject=message.subject)
            return True
        except Exception as exc:
            logger.error("email.smtp_error", error=str(exc))
            return False
