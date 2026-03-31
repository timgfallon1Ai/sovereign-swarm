"""Data models for the Calendar/Scheduling agent."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class CalendarEvent(BaseModel):
    """A calendar event from any provider."""

    id: str
    title: str
    description: str = ""
    start_time: datetime
    end_time: datetime
    location: str = ""
    attendees: list[str] = Field(default_factory=list)
    calendar_source: str = "google"  # google / apple / outlook
    recurring: bool = False
    reminders: list[int] = Field(default_factory=list)  # minutes before
    url: str = ""
    metadata: dict = Field(default_factory=dict)


class ScheduleConflict(BaseModel):
    """Two overlapping events."""

    event_a_id: str
    event_b_id: str
    overlap_minutes: int
    severity: str = "medium"  # low / medium / high


class MeetingPrep(BaseModel):
    """Pre-meeting context bundle."""

    event_id: str
    relevant_context: str = ""  # from knowledge base
    attendee_notes: str = ""
    suggested_agenda: str = ""
    action_items_from_last: list[str] = Field(default_factory=list)
