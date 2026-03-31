"""Data models for the document intelligence subsystem."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class DocumentType(str, Enum):
    PDF = "pdf"
    DOCX = "docx"
    CONTRACT = "contract"
    FINANCIAL_STATEMENT = "financial_statement"
    INVOICE = "invoice"
    REPORT = "report"


class ExtractedContent(BaseModel):
    text: str = ""
    tables: list[list[list[str]]] = Field(default_factory=list)
    images: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    page_count: int = 0


class DocumentComparison(BaseModel):
    doc_a: str
    doc_b: str
    additions: list[str] = Field(default_factory=list)
    deletions: list[str] = Field(default_factory=list)
    modifications: list[dict[str, str]] = Field(default_factory=list)
    similarity_score: float = 0.0


class DocumentSummary(BaseModel):
    title: str = ""
    key_points: list[str] = Field(default_factory=list)
    entities: list[str] = Field(default_factory=list)
    dates: list[str] = Field(default_factory=list)
    amounts: list[str] = Field(default_factory=list)
    action_items: list[str] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=datetime.utcnow)
