"""Data models for the Recruitment/HR agent."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class JobStatus(str, Enum):
    DRAFT = "draft"
    OPEN = "open"
    CLOSED = "closed"
    ON_HOLD = "on_hold"
    FILLED = "filled"


class CandidateStage(str, Enum):
    APPLIED = "applied"
    SCREENING = "screening"
    PHONE_SCREEN = "phone_screen"
    INTERVIEW = "interview"
    FINAL_ROUND = "final_round"
    OFFER = "offer"
    HIRED = "hired"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"


class InterviewType(str, Enum):
    PHONE = "phone"
    VIDEO = "video"
    IN_PERSON = "in_person"
    TECHNICAL = "technical"
    PANEL = "panel"


class OnboardingItemStatus(str, Enum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    BLOCKED = "blocked"


class JobPosting(BaseModel):
    """A job posting for recruitment."""

    id: str = ""
    title: str
    description: str
    requirements: list[str] = Field(default_factory=list)
    nice_to_haves: list[str] = Field(default_factory=list)
    benefits: list[str] = Field(default_factory=list)
    location: str = ""
    salary_range: str = ""
    employment_type: str = "full_time"  # full_time, part_time, contract
    status: JobStatus = JobStatus.DRAFT
    department: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now())


class Candidate(BaseModel):
    """A candidate in the hiring pipeline."""

    id: str = ""
    name: str
    email: str = ""
    phone: str = ""
    resume_summary: str = ""
    score: float = 0.0  # 0-100
    stage: CandidateStage = CandidateStage.APPLIED
    notes: list[str] = Field(default_factory=list)
    applied_for: str = ""  # job posting ID or title
    applied_at: datetime = Field(default_factory=lambda: datetime.now())


class InterviewSchedule(BaseModel):
    """A scheduled interview."""

    id: str = ""
    candidate_id: str
    candidate_name: str = ""
    interview_datetime: datetime
    interviewer: str
    interview_type: InterviewType = InterviewType.VIDEO
    location: str = ""
    notes: str = ""
    duration_minutes: int = 60


class OnboardingItem(BaseModel):
    """A single onboarding checklist item."""

    name: str
    description: str = ""
    status: OnboardingItemStatus = OnboardingItemStatus.NOT_STARTED
    assigned_to: str = ""
    due_date: datetime | None = None


class OnboardingChecklist(BaseModel):
    """An onboarding checklist for a new hire."""

    employee_name: str
    role: str
    start_date: datetime | None = None
    items: list[OnboardingItem] = Field(default_factory=list)
    completion_pct: float = 0.0
