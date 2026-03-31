"""Core data models for the task execution runtime."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class TaskStatus(str, Enum):
    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"
    WAITING_APPROVAL = "waiting_approval"
    CHECKPOINTED = "checkpointed"


class TaskNode(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    description: str
    status: TaskStatus = TaskStatus.PENDING
    assigned_agent: str
    input_data: dict[str, Any] = Field(default_factory=dict)
    output_data: dict[str, Any] = Field(default_factory=dict)
    dependencies: list[str] = Field(default_factory=list)  # node IDs
    start_time: datetime | None = None
    end_time: datetime | None = None
    error: str | None = None
    retry_count: int = 0
    max_retries: int = 2
    timeout_seconds: int = 300
    requires_approval: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class TaskGraphModel(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    goal: str
    nodes: dict[str, TaskNode] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: datetime | None = None
    status: TaskStatus = TaskStatus.PENDING
    user_id: str = ""
    conversation_id: str = ""


class TaskCheckpoint(BaseModel):
    graph_id: str
    graph_json: str
    last_updated: datetime = Field(default_factory=datetime.utcnow)
    version: int = 1
