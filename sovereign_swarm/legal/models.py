"""Data models for the legal / compliance subsystem."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ContractType(str, Enum):
    SERVICE_AGREEMENT = "service_agreement"
    NDA = "nda"
    DPA = "dpa"
    TERMS_OF_SERVICE = "terms_of_service"
    PRIVACY_POLICY = "privacy_policy"
    EMPLOYMENT = "employment"


class ComplianceCheck(BaseModel):
    area: str  # trading, data, financial, employment
    status: str = "pass"  # pass, warning, fail
    issues: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)


class RegulatoryAlert(BaseModel):
    regulation: str
    change_description: str = ""
    impact: str = ""  # low, medium, high
    action_required: str = ""
    deadline: datetime | None = None
    source_url: str = ""


class ContractDraft(BaseModel):
    type: ContractType
    parties: list[str] = Field(default_factory=list)
    key_terms: dict[str, Any] = Field(default_factory=dict)
    full_text: str = ""
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    review_required: bool = True


class TaxDocument(BaseModel):
    type: str  # quarterly_estimate, annual_return, 1099, w2
    period: str = ""  # e.g. "2026-Q1"
    estimated_amount: float = 0.0
    due_date: datetime | None = None
    status: str = "pending"  # pending, filed, overdue
