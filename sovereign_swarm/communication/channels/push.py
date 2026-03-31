"""Push notification channel — Apple Push Notifications (Phase B stub)."""

from __future__ import annotations

import structlog

from sovereign_swarm.communication.models import OutboundMessage

logger = structlog.get_logger()


class PushChannel:
    """Send push notifications to iOS app. Phase B implementation."""

    async def send(self, message: OutboundMessage) -> bool:
        """Send push notification to iOS app. Phase B implementation."""
        raise NotImplementedError("Push notifications not yet implemented — Phase B")
