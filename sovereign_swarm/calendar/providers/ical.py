"""iCal/CalDAV provider for Apple Calendar integration."""

from __future__ import annotations

from datetime import datetime

import structlog

from sovereign_swarm.calendar.models import CalendarEvent

logger = structlog.get_logger()


class ICalProvider:
    """iCal/CalDAV provider for Apple Calendar integration.

    Phase A: Stub.
    Phase B: Parse .ics files and/or connect via CalDAV.
    """

    def __init__(self, ics_path: str | None = None, caldav_url: str | None = None):
        self.ics_path = ics_path
        self.caldav_url = caldav_url

    async def get_events(
        self, start: datetime, end: datetime
    ) -> list[CalendarEvent]:
        """Fetch events in a date range from iCal/CalDAV."""
        logger.debug(
            "ical.get_events",
            start=start.isoformat(),
            end=end.isoformat(),
        )
        # Phase A stub
        return []
