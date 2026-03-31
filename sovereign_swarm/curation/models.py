"""Data models for the knowledge curation subsystem."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class DuplicateCluster(BaseModel):
    document_ids: list[str] = Field(default_factory=list)
    similarity_score: float = 0.0
    recommended_action: str = "review"  # keep_best, merge, remove, review


class OutdatedDocument(BaseModel):
    document_id: str
    reason: str = ""
    superseded_by: str = ""
    confidence: float = 0.0


class TopicTaxonomy(BaseModel):
    name: str
    subtopics: list[str] = Field(default_factory=list)
    document_count: int = 0


class ReadingList(BaseModel):
    title: str
    documents: list[dict[str, Any]] = Field(default_factory=list)
    estimated_time_hours: float = 0.0
    difficulty: str = "intermediate"  # beginner, intermediate, advanced
    description: str = ""


class QualityReport(BaseModel):
    source: str
    document_count: int = 0
    avg_quality_score: float = 0.0
    low_quality_count: int = 0
    issues: list[str] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=datetime.utcnow)
