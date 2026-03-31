"""Data models for the workflow automation subsystem."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class TriggerType(str, Enum):
    SCHEDULE = "schedule"
    WEBHOOK = "webhook"
    EVENT = "event"
    MANUAL = "manual"


class ActionType(str, Enum):
    SEND_MESSAGE = "send_message"
    RUN_AGENT = "run_agent"
    API_CALL = "api_call"
    UPDATE_DATABASE = "update_database"
    FILE_OPERATION = "file_operation"


class WorkflowTrigger(BaseModel):
    type: TriggerType
    config: dict[str, Any] = Field(default_factory=dict)


class WorkflowAction(BaseModel):
    type: ActionType
    config: dict[str, Any] = Field(default_factory=dict)
    timeout_seconds: int = 300


class WorkflowStep(BaseModel):
    name: str
    action: WorkflowAction
    conditions: dict[str, Any] = Field(default_factory=dict)
    on_success: str = ""  # next step name or "" for end
    on_failure: str = ""  # failure step name or "" for abort


class Workflow(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    description: str = ""
    trigger: WorkflowTrigger
    steps: list[WorkflowStep] = Field(default_factory=list)
    enabled: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_run: datetime | None = None
    run_count: int = 0


class WorkflowRun(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    workflow_id: str
    started_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: datetime | None = None
    status: str = "running"  # running, completed, failed, cancelled
    step_results: list[dict[str, Any]] = Field(default_factory=list)
