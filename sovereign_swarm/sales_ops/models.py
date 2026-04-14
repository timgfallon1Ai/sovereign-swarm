"""Data models for the sales_ops module.

Pydantic models for CRM entities (Contact, Company, Opportunity, Activity)
plus sequence execution models (SequenceEnrollment, ScheduledMessage).
Tenant-aware: every record carries a `tenant` key that matches the
TENANTS dict in `sovereign_swarm/marketing/brand.py`.
"""

from __future__ import annotations

import json
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class ContactSource(str, Enum):
    APOLLO = "apollo"
    CSV = "csv"
    MANUAL = "manual"
    REFERRAL = "referral"
    WEB_FORM = "web_form"


class OpportunityStage(str, Enum):
    COLD = "cold"
    AWARE = "aware"
    ENGAGED = "engaged"
    MQL = "mql"
    SQL = "sql"
    OPPORTUNITY = "opportunity"
    CLOSE = "close"
    WON = "won"
    LOST = "lost"


class ActivityType(str, Enum):
    EMAIL_SENT = "email_sent"
    EMAIL_OPENED = "email_opened"
    EMAIL_CLICKED = "email_clicked"
    EMAIL_REPLIED = "email_replied"
    CALL_ATTEMPTED = "call_attempted"
    CALL_COMPLETED = "call_completed"
    SMS_SENT = "sms_sent"
    SMS_REPLIED = "sms_replied"
    LINKEDIN_CONNECTION = "linkedin_connection"
    LINKEDIN_MESSAGE = "linkedin_message"
    NOTE = "note"
    SAMPLE_SHIPPED = "sample_shipped"
    MEETING_BOOKED = "meeting_booked"
    UNSUBSCRIBED = "unsubscribed"


class EnrollmentStatus(str, Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    EXITED = "exited"


class MessageStatus(str, Enum):
    DRAFTED = "drafted"
    APPROVED = "approved"
    SENT = "sent"
    FAILED = "failed"
    SKIPPED = "skipped"


class MessageChannel(str, Enum):
    EMAIL = "email"
    SMS = "sms"
    LINKEDIN = "linkedin"
    CALL = "call"
    MANUAL = "manual"  # e.g., a reminder to do something offline


# ---------------------------------------------------------------------------
# Core entities
# ---------------------------------------------------------------------------


class Company(BaseModel):
    id: int | None = None
    tenant: str
    name: str
    domain: str = ""
    industry: str = ""
    size: str = ""  # "1-10", "11-50", "51-200", etc.
    region: str = ""
    notes: str = ""
    source: ContactSource = ContactSource.MANUAL
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Contact(BaseModel):
    id: int | None = None
    tenant: str
    company_id: int | None = None
    email: str = ""
    phone: str = ""
    first_name: str = ""
    last_name: str = ""
    role: str = ""  # "facility manager", "procurement", "VP ops"
    linkedin_url: str = ""
    source: ContactSource = ContactSource.MANUAL
    tags: list[str] = Field(default_factory=list)
    consent_sms: bool = False
    unsubscribed: bool = False
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()

    @property
    def display(self) -> str:
        name = self.full_name or self.email or "(unknown)"
        if self.role:
            return f"{name} ({self.role})"
        return name


class Opportunity(BaseModel):
    id: int | None = None
    tenant: str
    contact_id: int
    company_id: int | None = None
    stage: OpportunityStage = OpportunityStage.COLD
    value_cents: int = 0
    close_date: str = ""  # ISO date string
    probability: float = 0.0
    notes: str = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    @property
    def value_usd(self) -> float:
        return self.value_cents / 100.0


class Activity(BaseModel):
    id: int | None = None
    tenant: str
    contact_id: int
    opportunity_id: int | None = None
    type: ActivityType
    channel: str = ""
    subject: str = ""
    body: str = ""
    outcome: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
    occurred_at: datetime = Field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# Sequence execution
# ---------------------------------------------------------------------------


class SequenceEnrollment(BaseModel):
    id: int | None = None
    tenant: str
    contact_id: int
    sequence_name: str
    current_step: int = 0
    status: EnrollmentStatus = EnrollmentStatus.ACTIVE
    exit_reason: str = ""
    next_action_at: datetime | None = None
    enrolled_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: datetime | None = None


class ScheduledMessage(BaseModel):
    id: int | None = None
    tenant: str
    enrollment_id: int
    contact_id: int
    step_index: int
    channel: MessageChannel
    subject: str = ""
    body: str = ""
    status: MessageStatus = MessageStatus.DRAFTED
    scheduled_for: datetime | None = None
    approved_at: datetime | None = None
    sent_at: datetime | None = None
    reply_received_at: datetime | None = None
    error: str = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)

    @field_validator("status", mode="before")
    @classmethod
    def _coerce_status(cls, v: Any) -> Any:
        if isinstance(v, str):
            return MessageStatus(v)
        return v


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def serialize_tags(tags: list[str]) -> str:
    """Serialize tag list for SQLite storage."""
    return json.dumps(tags or [])


def deserialize_tags(raw: str | None) -> list[str]:
    """Deserialize tag list from SQLite storage."""
    if not raw:
        return []
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []


def serialize_metadata(metadata: dict[str, Any]) -> str:
    """Serialize metadata dict for SQLite storage."""
    return json.dumps(metadata or {}, default=str)


def deserialize_metadata(raw: str | None) -> dict[str, Any]:
    """Deserialize metadata dict from SQLite storage."""
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}
