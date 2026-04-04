"""Pydantic models for the MedicalAgent domain."""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class MedicalDomain(str, Enum):
    RADIOLOGY = "radiology"
    ONCOLOGY = "oncology"
    DENTISTRY = "dentistry"
    ORTHOPEDICS = "orthopedics"
    PHARMACOLOGY = "pharmacology"
    REGENERATIVE_MEDICINE = "regenerative_medicine"
    NEUROSCIENCE = "neuroscience"
    CELLULAR_BIOLOGY = "cellular_biology"
    GENERAL = "general"


class MedicalQuery(BaseModel):
    """Structured medical query."""

    domain: MedicalDomain = MedicalDomain.GENERAL
    query_text: str
    image_path: Optional[str] = None
    patient_context: Optional[Dict[str, Any]] = None


class DrugInteraction(BaseModel):
    """A known or inferred drug-drug interaction."""

    drug_a: str
    drug_b: str
    severity: str = Field(
        ...,
        description="Interaction severity",
        pattern="^(mild|moderate|severe|contraindicated)$",
    )
    description: str = ""
    mechanism: str = ""


class ImagingAnalysis(BaseModel):
    """Result of medical image analysis."""

    modality: str = Field(
        ...,
        description="Imaging modality",
        pattern="^(xray|ct|mri|ultrasound|histopath)$",
    )
    findings: List[str] = Field(default_factory=list)
    impression: str = ""
    confidence: float = 0.0
    regions_of_interest: List[str] = Field(default_factory=list)


class ClinicalResearchResult(BaseModel):
    """A single result from medical literature search."""

    title: str
    source: str = Field(
        ...,
        description="Literature source",
        pattern="^(pubmed|clinicaltrials)$",
    )
    summary: str = ""
    relevance_score: float = 0.0
    pmid_or_nctid: str = ""
    url: str = ""


MEDICAL_DISCLAIMER = (
    "This is not medical advice. Consult a healthcare professional."
)


class MedicalReport(BaseModel):
    """Structured medical report with mandatory disclaimer."""

    domain: MedicalDomain = MedicalDomain.GENERAL
    query: str
    findings: str
    recommendations: str = ""
    references: List[str] = Field(default_factory=list)
    disclaimer: str = MEDICAL_DISCLAIMER
