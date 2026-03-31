"""Data models for the digital twin subsystem."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class DecisionPattern(BaseModel):
    domain: str  # trading, hiring, design, engineering, etc.
    pattern_description: str = ""
    frequency: int = 0  # how many times this pattern has been observed
    confidence: float = 0.0
    examples: list[str] = Field(default_factory=list)


class CognitiveSnapshot(BaseModel):
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    active_projects: list[str] = Field(default_factory=list)
    decision_patterns: list[DecisionPattern] = Field(default_factory=list)
    communication_style: dict[str, Any] = Field(default_factory=dict)
    risk_tolerance: dict[str, float] = Field(default_factory=dict)  # domain -> 0-1
    expertise_areas: list[str] = Field(default_factory=list)


class DelegateQuery(BaseModel):
    query: str
    requester: str = ""
    access_level: str = "viewer"  # viewer, operator, admin
    context: dict[str, Any] = Field(default_factory=dict)


class DelegateResponse(BaseModel):
    response: str = ""
    confidence: float = 0.0
    sources: list[str] = Field(default_factory=list)
    disclaimer: str = "This is an AI-generated response based on Tim's patterns and knowledge."


class ContinuityProtocol(BaseModel):
    active: bool = False
    boundaries: list[str] = Field(
        default_factory=lambda: [
            "No financial transactions",
            "No client-facing communications",
            "No code deployments",
            "No hiring decisions",
            "No contract signing",
        ]
    )
    auto_responses_enabled: bool = False
    escalation_contacts: list[dict[str, str]] = Field(default_factory=list)
    max_autonomy_level: str = "viewer"  # viewer, operator (never admin without Tim)
    activated_at: datetime | None = None
    queued_decisions: list[dict[str, Any]] = Field(default_factory=list)
