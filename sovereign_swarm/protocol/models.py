"""Inter-agent messaging and permission models."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class AgentMessage(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    from_agent: str
    to_agent: str
    message_type: str  # "task_request", "task_response", "status_update", "coordination"
    payload: dict = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    signature: str = ""
    graph_id: str = ""
    node_id: str = ""


class Permission(BaseModel):
    agent_name: str
    action: str
    level: str  # "auto", "auto_notify", "requires_approval", "manual_only"
    max_value: float | None = None
    daily_limit: float | None = None
