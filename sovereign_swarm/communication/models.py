"""Data models for the communication agent."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class Channel(str, Enum):
    EMAIL = "email"
    SMS = "sms"
    SLACK = "slack"
    WHATSAPP = "whatsapp"
    PUSH_NOTIFICATION = "push_notification"


class MessagePriority(str, Enum):
    URGENT = "urgent"
    NORMAL = "normal"
    LOW = "low"


class MessageStatus(str, Enum):
    DRAFT = "draft"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    SENT = "sent"
    FAILED = "failed"
    CANCELLED = "cancelled"


class OutboundMessage(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    channel: Channel
    to: list[str] = Field(default_factory=list)
    cc: list[str] = Field(default_factory=list)
    subject: str = ""
    body: str = ""
    html_body: str = ""
    attachments: list[str] = Field(default_factory=list)
    priority: MessagePriority = MessagePriority.NORMAL
    status: MessageStatus = MessageStatus.DRAFT
    requires_approval: bool = False
    approved_by: str | None = None
    sent_at: datetime | None = None
    error: str | None = None
    thread_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class MessageTemplate(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    name: str
    channel: Channel
    subject_template: str = ""
    body_template: str = ""
    variables: list[str] = Field(default_factory=list)


class ThreadSummary(BaseModel):
    thread_id: str
    channel: Channel
    participants: list[str] = Field(default_factory=list)
    message_count: int = 0
    last_message_at: datetime | None = None
    subject: str = ""
