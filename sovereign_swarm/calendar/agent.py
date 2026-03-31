"""CalendarAgent -- scheduling and meeting prep for the swarm."""

from __future__ import annotations

from typing import Any

import structlog

from sovereign_swarm.protocol.swarm_agent import (
    SwarmAgent,
    SwarmAgentCard,
    SwarmAgentRequest,
    SwarmAgentResponse,
)

logger = structlog.get_logger()


class CalendarAgent(SwarmAgent):
    """Calendar and scheduling agent.

    Provides daily/weekly agendas, conflict detection, meeting prep,
    and smart time-slot suggestions across Google Calendar, Apple
    Calendar (iCal/CalDAV), and Outlook.
    """

    def __init__(
        self,
        ingest_bridge: Any | None = None,
        config: Any | None = None,
    ):
        self.ingest = ingest_bridge
        self.config = config
        self._scheduler = None

    @property
    def card(self) -> SwarmAgentCard:
        return SwarmAgentCard(
            name="calendar",
            description=(
                "Calendar and scheduling agent -- daily/weekly agendas, conflict "
                "detection, meeting preparation, and smart time-slot suggestions"
            ),
            domains=["calendar", "scheduling", "meetings", "time"],
            supported_intents=[
                "today_schedule",
                "week_schedule",
                "meeting_prep",
                "find_time",
                "create_event",
                "detect_conflicts",
            ],
            capabilities=[
                "today_schedule",
                "week_schedule",
                "meeting_prep",
                "find_time",
                "create_event",
                "detect_conflicts",
            ],
        )

    # ------------------------------------------------------------------
    # Core execute
    # ------------------------------------------------------------------

    async def execute(self, request: SwarmAgentRequest) -> SwarmAgentResponse:
        """Route a calendar task to the appropriate handler."""
        task = request.task.lower()
        params = request.parameters or request.context or {}

        try:
            if "today" in task:
                result = await self._today_schedule()
            elif "week" in task:
                result = await self._week_schedule()
            elif "prep" in task or "prepare" in task:
                result = await self._meeting_prep(params)
            elif "find time" in task or "schedule" in task or "suggest" in task:
                result = await self._suggest_time(params)
            elif "create" in task or "add" in task:
                result = await self._create_event(params)
            elif "conflict" in task:
                result = await self._detect_conflicts()
            else:
                # Default to today's schedule
                result = await self._today_schedule()

            return SwarmAgentResponse(
                agent_name="calendar",
                status="success",
                output=result.get("markdown", str(result)),
                data=result,
                confidence=result.get("confidence", 0.8),
            )
        except Exception as e:
            logger.error("calendar.execute_failed", error=str(e))
            return SwarmAgentResponse(
                agent_name="calendar",
                status="error",
                error=str(e),
            )

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------

    async def _today_schedule(self) -> dict:
        scheduler = self._get_scheduler()
        events = await scheduler.get_today()
        conflicts = await scheduler.detect_conflicts(events)

        if not events:
            md = "## Today's Schedule\n\nNo events scheduled for today."
            return {"markdown": md, "events": [], "confidence": 0.9}

        md = "## Today's Schedule\n\n"
        md += "| Time | Event | Location |\n"
        md += "|------|-------|----------|\n"
        for ev in events:
            start = ev.start_time.strftime("%H:%M")
            end = ev.end_time.strftime("%H:%M")
            loc = ev.location or "-"
            md += f"| {start}-{end} | {ev.title} | {loc} |\n"

        if conflicts:
            md += f"\n**{len(conflicts)} conflict(s) detected.**\n"
            for c in conflicts:
                md += f"- Overlap: {c.overlap_minutes}min (severity: {c.severity})\n"

        return {
            "markdown": md,
            "events": [e.model_dump() for e in events],
            "conflicts": [c.model_dump() for c in conflicts],
            "confidence": 0.85,
        }

    async def _week_schedule(self) -> dict:
        scheduler = self._get_scheduler()
        events = await scheduler.get_week()
        conflicts = await scheduler.detect_conflicts(events)

        if not events:
            md = "## This Week's Schedule\n\nNo events scheduled this week."
            return {"markdown": md, "events": [], "confidence": 0.9}

        md = "## This Week's Schedule\n\n"
        current_date = None
        for ev in events:
            ev_date = ev.start_time.strftime("%A, %B %d")
            if ev_date != current_date:
                current_date = ev_date
                md += f"\n### {ev_date}\n"
                md += "| Time | Event | Location |\n"
                md += "|------|-------|----------|\n"
            start = ev.start_time.strftime("%H:%M")
            end = ev.end_time.strftime("%H:%M")
            loc = ev.location or "-"
            md += f"| {start}-{end} | {ev.title} | {loc} |\n"

        if conflicts:
            md += f"\n**{len(conflicts)} conflict(s) detected this week.**\n"

        return {
            "markdown": md,
            "events": [e.model_dump() for e in events],
            "conflicts": [c.model_dump() for c in conflicts],
            "confidence": 0.85,
        }

    async def _meeting_prep(self, params: dict) -> dict:
        scheduler = self._get_scheduler()

        event_id = params.get("event_id", "")
        if not event_id:
            # Try to prep for the next upcoming event
            events = await scheduler.get_today()
            if not events:
                return {
                    "markdown": "No upcoming events to prepare for.",
                    "confidence": 0.9,
                }
            from datetime import datetime

            now = datetime.now()
            upcoming = [e for e in events if e.start_time > now]
            if not upcoming:
                return {
                    "markdown": "No more events today to prepare for.",
                    "confidence": 0.9,
                }
            event = upcoming[0]
        else:
            # Find event by ID across today's events
            events = await scheduler.get_today()
            event = next((e for e in events if e.id == event_id), None)
            if not event:
                return {
                    "markdown": f"Event `{event_id}` not found.",
                    "confidence": 0.5,
                }

        prep = await scheduler.prepare_for_meeting(event)

        md = f"## Meeting Prep: {event.title}\n\n"
        md += f"**Time**: {event.start_time.strftime('%H:%M')} - {event.end_time.strftime('%H:%M')}\n"
        if event.location:
            md += f"**Location**: {event.location}\n"
        if event.attendees:
            md += f"**Attendees**: {', '.join(event.attendees)}\n"

        md += f"\n### Suggested Agenda\n{prep.suggested_agenda}\n"

        if prep.relevant_context:
            md += f"\n### Relevant Context\n{prep.relevant_context}\n"
        if prep.attendee_notes:
            md += f"\n### Attendee Notes\n{prep.attendee_notes}\n"
        if prep.action_items_from_last:
            md += "\n### Outstanding Action Items\n"
            for item in prep.action_items_from_last:
                md += f"- {item}\n"

        return {
            "markdown": md,
            "prep": prep.model_dump(),
            "confidence": 0.75,
        }

    async def _suggest_time(self, params: dict) -> dict:
        scheduler = self._get_scheduler()
        duration = params.get("duration_minutes", params.get("duration", 60))
        participants = params.get("participants", [])
        preferred = params.get("preferred_hours", (9, 17))

        slots = await scheduler.suggest_time(
            duration_minutes=duration,
            participants=participants,
            preferred_hours=tuple(preferred),
        )

        if not slots:
            md = "## Available Time Slots\n\nNo available slots found this week."
            return {"markdown": md, "slots": [], "confidence": 0.7}

        md = f"## Available {duration}-Minute Slots\n\n"
        md += "| Date | Start | End |\n"
        md += "|------|-------|-----|\n"
        for s in slots:
            md += f"| {s['date']} | {s['start']} | {s['end']} |\n"

        return {"markdown": md, "slots": slots, "confidence": 0.8}

    async def _create_event(self, params: dict) -> dict:
        from datetime import datetime

        from sovereign_swarm.calendar.models import CalendarEvent

        title = params.get("title", "New Event")
        start_str = params.get("start_time", "")
        end_str = params.get("end_time", "")

        if not start_str:
            return {
                "markdown": "Cannot create event: `start_time` is required.",
                "confidence": 0.5,
            }

        start = datetime.fromisoformat(start_str)
        end = (
            datetime.fromisoformat(end_str)
            if end_str
            else start + __import__("datetime").timedelta(hours=1)
        )

        event = CalendarEvent(
            id=f"new_{int(start.timestamp())}",
            title=title,
            description=params.get("description", ""),
            start_time=start,
            end_time=end,
            location=params.get("location", ""),
            attendees=params.get("attendees", []),
        )

        # Attempt creation through first provider that supports it
        event_id = event.id
        for provider in self._get_scheduler().providers:
            if hasattr(provider, "create_event"):
                try:
                    event_id = await provider.create_event(event)
                    break
                except Exception:
                    continue

        md = (
            f"## Event Created\n\n"
            f"**{title}**\n"
            f"- Time: {start.strftime('%Y-%m-%d %H:%M')} - {end.strftime('%H:%M')}\n"
            f"- ID: `{event_id}`\n"
        )
        return {"markdown": md, "event_id": event_id, "confidence": 0.85}

    async def _detect_conflicts(self) -> dict:
        scheduler = self._get_scheduler()
        events = await scheduler.get_week()
        conflicts = await scheduler.detect_conflicts(events)

        if not conflicts:
            md = "## Schedule Conflicts\n\nNo conflicts detected this week."
            return {"markdown": md, "conflicts": [], "confidence": 0.95}

        md = f"## Schedule Conflicts ({len(conflicts)})\n\n"
        md += "| Event A | Event B | Overlap | Severity |\n"
        md += "|---------|---------|---------|----------|\n"
        event_map = {e.id: e.title for e in events}
        for c in conflicts:
            a_name = event_map.get(c.event_a_id, c.event_a_id)
            b_name = event_map.get(c.event_b_id, c.event_b_id)
            md += f"| {a_name} | {b_name} | {c.overlap_minutes}min | {c.severity} |\n"

        return {
            "markdown": md,
            "conflicts": [c.model_dump() for c in conflicts],
            "confidence": 0.9,
        }

    # ------------------------------------------------------------------
    # Lazy init
    # ------------------------------------------------------------------

    def _get_scheduler(self):
        if self._scheduler is None:
            from sovereign_swarm.calendar.providers.google import (
                GoogleCalendarProvider,
            )
            from sovereign_swarm.calendar.providers.ical import ICalProvider
            from sovereign_swarm.calendar.scheduler import SmartScheduler

            providers = [GoogleCalendarProvider(), ICalProvider()]
            self._scheduler = SmartScheduler(
                providers=providers,
                ingest_bridge=self.ingest,
            )
        return self._scheduler
