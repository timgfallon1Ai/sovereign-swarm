"""Smart scheduling logic with conflict detection and meeting prep."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import structlog

from sovereign_swarm.calendar.models import (
    CalendarEvent,
    MeetingPrep,
    ScheduleConflict,
)

logger = structlog.get_logger()


class SmartScheduler:
    """Intelligent scheduling with conflict detection and meeting prep."""

    def __init__(
        self,
        providers: list[Any] | None = None,
        ingest_bridge: Any | None = None,
    ):
        self.providers = providers or []
        self.ingest = ingest_bridge

    # ------------------------------------------------------------------
    # Event retrieval
    # ------------------------------------------------------------------

    async def get_today(self) -> list[CalendarEvent]:
        """Get all events for today across all providers."""
        now = datetime.now()
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)
        return await self._aggregate_events(start, end)

    async def get_week(self) -> list[CalendarEvent]:
        """Get all events for the current week across all providers."""
        now = datetime.now()
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        # Start from Monday of this week
        start -= timedelta(days=start.weekday())
        end = start + timedelta(days=7)
        return await self._aggregate_events(start, end)

    async def _aggregate_events(
        self, start: datetime, end: datetime
    ) -> list[CalendarEvent]:
        """Collect events from every provider and sort by start time."""
        all_events: list[CalendarEvent] = []
        for provider in self.providers:
            try:
                events = await provider.get_events(start, end)
                all_events.extend(events)
            except Exception as exc:
                logger.warning(
                    "scheduler.provider_error",
                    provider=type(provider).__name__,
                    error=str(exc),
                )
        all_events.sort(key=lambda e: e.start_time)
        return all_events

    # ------------------------------------------------------------------
    # Conflict detection
    # ------------------------------------------------------------------

    async def detect_conflicts(
        self, events: list[CalendarEvent]
    ) -> list[ScheduleConflict]:
        """Find overlapping events."""
        conflicts: list[ScheduleConflict] = []
        sorted_events = sorted(events, key=lambda e: e.start_time)
        for i, a in enumerate(sorted_events):
            for b in sorted_events[i + 1 :]:
                if b.start_time >= a.end_time:
                    break
                overlap = (min(a.end_time, b.end_time) - b.start_time).seconds // 60
                severity = "low"
                if overlap > 30:
                    severity = "medium"
                if overlap > 60:
                    severity = "high"
                conflicts.append(
                    ScheduleConflict(
                        event_a_id=a.id,
                        event_b_id=b.id,
                        overlap_minutes=overlap,
                        severity=severity,
                    )
                )
        return conflicts

    # ------------------------------------------------------------------
    # Meeting preparation
    # ------------------------------------------------------------------

    async def prepare_for_meeting(self, event: CalendarEvent) -> MeetingPrep:
        """Pull relevant context from knowledge base for an upcoming meeting."""
        relevant_context = ""
        attendee_notes = ""

        if self.ingest:
            # Search sovereign-ingest for context on topic
            try:
                results = await self.ingest.search(event.title, limit=5)
                if results:
                    relevant_context = "\n".join(
                        r.get("text", str(r)) for r in results[:3]
                    )
            except Exception as exc:
                logger.debug("scheduler.ingest_search_failed", error=str(exc))

            # Search for attendee context
            for attendee in event.attendees:
                try:
                    results = await self.ingest.search(attendee, limit=2)
                    if results:
                        attendee_notes += f"\n**{attendee}**: "
                        attendee_notes += results[0].get("text", "")[:200]
                except Exception:
                    pass

        suggested_agenda = (
            f"1. Welcome & introductions\n"
            f"2. {event.title}\n"
            f"3. Discussion\n"
            f"4. Action items & next steps"
        )

        return MeetingPrep(
            event_id=event.id,
            relevant_context=relevant_context,
            attendee_notes=attendee_notes,
            suggested_agenda=suggested_agenda,
            action_items_from_last=[],
        )

    # ------------------------------------------------------------------
    # Time suggestion
    # ------------------------------------------------------------------

    async def suggest_time(
        self,
        duration_minutes: int,
        participants: list[str] | None = None,
        preferred_hours: tuple[int, int] = (9, 17),
    ) -> list[dict]:
        """Suggest available meeting times."""
        today = datetime.now()
        events = await self.get_week()
        suggestions: list[dict] = []

        for day_offset in range(7):
            date = today + timedelta(days=day_offset)
            start_hour, end_hour = preferred_hours
            day_start = date.replace(
                hour=start_hour, minute=0, second=0, microsecond=0
            )
            day_end = date.replace(
                hour=end_hour, minute=0, second=0, microsecond=0
            )

            # Get busy blocks for this day
            day_events = [
                e
                for e in events
                if e.start_time.date() == date.date()
            ]

            # Find gaps
            cursor = day_start
            for ev in sorted(day_events, key=lambda e: e.start_time):
                if ev.start_time > cursor:
                    gap = (ev.start_time - cursor).seconds // 60
                    if gap >= duration_minutes:
                        suggestions.append(
                            {
                                "date": date.strftime("%Y-%m-%d"),
                                "start": cursor.strftime("%H:%M"),
                                "end": (
                                    cursor + timedelta(minutes=duration_minutes)
                                ).strftime("%H:%M"),
                                "duration_minutes": duration_minutes,
                            }
                        )
                cursor = max(cursor, ev.end_time)

            # After last event
            if cursor < day_end:
                gap = (day_end - cursor).seconds // 60
                if gap >= duration_minutes:
                    suggestions.append(
                        {
                            "date": date.strftime("%Y-%m-%d"),
                            "start": cursor.strftime("%H:%M"),
                            "end": (
                                cursor + timedelta(minutes=duration_minutes)
                            ).strftime("%H:%M"),
                            "duration_minutes": duration_minutes,
                        }
                    )

        return suggestions[:10]  # top 10 slots

    # ------------------------------------------------------------------
    # Reminders
    # ------------------------------------------------------------------

    async def create_reminder(
        self, event_id: str, minutes_before: int, message: str
    ) -> dict:
        """Create a reminder for an event."""
        logger.info(
            "scheduler.create_reminder",
            event_id=event_id,
            minutes_before=minutes_before,
        )
        return {
            "event_id": event_id,
            "minutes_before": minutes_before,
            "message": message,
            "status": "created",
        }
