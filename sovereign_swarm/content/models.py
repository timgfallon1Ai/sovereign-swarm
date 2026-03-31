"""Data models for the Content Creation agent."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ContentType(str, Enum):
    BLOG_POST = "blog_post"
    SOCIAL_POST = "social_post"
    EMAIL_SEQUENCE = "email_sequence"
    PRODUCT_DESCRIPTION = "product_description"
    VIDEO_SCRIPT = "video_script"
    PRESS_RELEASE = "press_release"


class ContentBrief(BaseModel):
    """Brief describing what content to create."""

    topic: str
    audience: str = "general"
    tone: str = "professional"
    keywords: list[str] = Field(default_factory=list)
    length: int = 1000  # target word count
    channel: str = "blog"
    content_type: ContentType = ContentType.BLOG_POST
    additional_notes: str = ""


class ContentDraft(BaseModel):
    """A generated content draft."""

    title: str
    body: str
    content_type: ContentType
    seo_score: float = 0.0  # 0-100
    readability_score: float = 0.0  # Flesch-Kincaid grade level
    word_count: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now())


class CalendarEntry(BaseModel):
    """A single content calendar entry."""

    date: datetime
    title: str
    content_type: ContentType
    channel: str
    status: str = "planned"  # planned, drafted, review, published
    assigned_to: str = ""
    notes: str = ""


class ContentCalendar(BaseModel):
    """A content calendar with scheduled entries."""

    name: str = "Content Calendar"
    entries: list[CalendarEntry] = Field(default_factory=list)
    start_date: datetime | None = None
    end_date: datetime | None = None
