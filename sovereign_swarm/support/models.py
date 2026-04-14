"""Data models for the support (case management) module.

A Case is a customer service thread. It's created when an inbound
email arrives (from SendGrid Inbound Parse) that doesn't match an
active sequence enrollment, OR manually by a user.

Each Case has a list of CaseMessage entries (the thread). Cases track
status, assignee, priority, and are tenant-scoped.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class CaseStatus(str, Enum):
    NEW = "new"              # just created, not yet triaged
    OPEN = "open"            # in progress
    PENDING = "pending"      # waiting on customer
    RESOLVED = "resolved"    # closed — resolution logged
    CLOSED = "closed"        # archived


class CasePriority(str, Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class CaseSource(str, Enum):
    EMAIL_INBOUND = "email_inbound"  # from SendGrid Inbound Parse
    MANUAL = "manual"                 # user created in UI
    API = "api"                       # external system
    SMS_INBOUND = "sms_inbound"       # from Twilio


class CaseMessageDirection(str, Enum):
    INBOUND = "inbound"     # from customer
    OUTBOUND = "outbound"   # from us


class Case(BaseModel):
    id: int | None = None
    tenant: str
    contact_id: int | None = None    # link to sales_ops.contacts if matched
    subject: str
    status: CaseStatus = CaseStatus.NEW
    priority: CasePriority = CasePriority.NORMAL
    source: CaseSource = CaseSource.EMAIL_INBOUND
    assigned_to: str = ""            # user email / name
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    resolved_at: datetime | None = None


class CaseMessage(BaseModel):
    id: int | None = None
    case_id: int
    tenant: str
    direction: CaseMessageDirection
    sender: str = ""       # email or name
    recipient: str = ""
    subject: str = ""
    body: str = ""
    channel: str = "email"  # email | sms | call | note
    metadata: dict[str, Any] = Field(default_factory=dict)
    occurred_at: datetime = Field(default_factory=datetime.utcnow)
