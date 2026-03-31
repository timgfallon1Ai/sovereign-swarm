"""Audit trail data models."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class AuditEntry:
    event_type: str
    agent_name: str
    action: str
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = field(default_factory=datetime.utcnow)
    graph_id: str = ""
    node_id: str = ""
    user_id: str = ""
    input_summary: str = ""
    output_summary: str = ""
    status: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
