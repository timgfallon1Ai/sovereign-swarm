"""Data models for the local model lab subsystem."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ModelConfig(BaseModel):
    name: str
    path: str = ""
    quantization: str = ""  # "", "4bit", "8bit", "GGUF-Q4_K_M", etc.
    context_length: int = 4096
    parameters_b: float = 0.0  # billions of parameters
    active: bool = False
    registered_at: datetime = Field(default_factory=datetime.utcnow)
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class BenchmarkResult(BaseModel):
    model_name: str
    task: str
    score: float = 0.0  # 0-1 quality score
    tokens_per_second: float = 0.0
    memory_gb: float = 0.0
    latency_ms: float = 0.0
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class BenchmarkSuite(BaseModel):
    name: str
    tasks: list[str] = Field(default_factory=list)
    results: list[BenchmarkResult] = Field(default_factory=list)
    best_model: str = ""


class ModelComparison(BaseModel):
    model_a: str
    model_b: str
    tasks: list[str] = Field(default_factory=list)
    winner_by_task: dict[str, str] = Field(default_factory=dict)
    overall_winner: str = ""
