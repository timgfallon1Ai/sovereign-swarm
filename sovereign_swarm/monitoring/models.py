"""Data models for the monitoring subsystem."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class ServiceStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    DOWN = "down"
    UNKNOWN = "unknown"


class ServiceCheck(BaseModel):
    service_name: str
    status: ServiceStatus
    response_time_ms: float = 0
    last_checked: datetime = Field(default_factory=datetime.utcnow)
    error: str = ""
    metadata: dict = Field(default_factory=dict)


class CostEntry(BaseModel):
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    service: str  # "claude_api", "railway", "pinecone", etc.
    agent_name: str = ""
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    model: str = ""


class Alert(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    severity: str  # "critical", "warning", "info"
    source: str  # service or agent name
    message: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    acknowledged: bool = False
    resolved: bool = False
    metadata: dict = Field(default_factory=dict)


class SystemSnapshot(BaseModel):
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    services: list[ServiceCheck] = Field(default_factory=list)
    active_agents: list[str] = Field(default_factory=list)
    active_tasks: int = 0
    knowledge_base_docs: int = 0
    knowledge_graph_nodes: int = 0
    skill_patches: int = 0
    daily_cost_usd: float = 0.0
    alerts: list[Alert] = Field(default_factory=list)
    overall_status: ServiceStatus = ServiceStatus.UNKNOWN
