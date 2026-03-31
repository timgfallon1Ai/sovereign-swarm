"""SMS channel — sends via Twilio."""

from __future__ import annotations

import os
from typing import Any

import structlog

from sovereign_swarm.communication.models import OutboundMessage

logger = structlog.get_logger()


class SMSChannel:
    """Send SMS messages via Twilio."""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        config = config or {}
        self._account_sid = config.get("twilio_sid") or os.getenv("TWILIO_SID", "")
        self._auth_token = config.get("twilio_token") or os.getenv("TWILIO_TOKEN", "")
        self._from_number = config.get("twilio_from_number") or os.getenv("TWILIO_FROM_NUMBER", "")

    async def send(self, message: OutboundMessage) -> bool:
        """Send SMS to all recipients via Twilio REST API."""
        if not all([self._account_sid, self._auth_token, self._from_number]):
            logger.error("sms.missing_config", msg="TWILIO_SID, TWILIO_TOKEN, or TWILIO_FROM_NUMBER not set")
            return False

        try:
            import httpx

            url = f"https://api.twilio.com/2010-04-01/Accounts/{self._account_sid}/Messages.json"
            all_ok = True

            async with httpx.AsyncClient() as client:
                for recipient in message.to:
                    resp = await client.post(
                        url,
                        data={
                            "From": self._from_number,
                            "To": recipient,
                            "Body": message.body,
                        },
                        auth=(self._account_sid, self._auth_token),
                    )
                    if resp.status_code == 201:
                        logger.info("sms.sent", to=recipient)
                    else:
                        logger.error("sms.failed", to=recipient, status=resp.status_code, body=resp.text)
                        all_ok = False

            return all_ok
        except Exception as exc:
            logger.error("sms.error", error=str(exc))
            return False
