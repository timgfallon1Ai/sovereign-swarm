from __future__ import annotations

from datetime import datetime
from typing import Any

import uuid
from pydantic import BaseModel, Field


class PatchTrigger(BaseModel):
    agent_name: str
    intent_pattern: str = ""  # regex
    domain_pattern: str = ""
    error_pattern: str = ""  # regex on error messages
    task_keywords: list[str] = Field(default_factory=list)


class SkillPatch(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    trigger: PatchTrigger
    context: str  # what situation this addresses
    instructions: str  # what to do differently
    source: str  # "failure_analysis", "success_capture", "consolidation"
    confidence: float = 0.5
    times_applied: int = 0
    times_succeeded: int = 0
    success_rate: float = 0.0
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_applied: datetime | None = None
    superseded_by: str | None = None
    tags: list[str] = Field(default_factory=list)


class SkillModule(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    description: str
    agent_name: str
    patches_consolidated: list[str] = Field(default_factory=list)  # source patch IDs
    system_prompt_addition: str = ""
    training_data: list[dict[str, Any]] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    quality_score: float = 0.0
