"""Data models for the scientist agent."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class HypothesisStatus(str, Enum):
    PROPOSED = "proposed"
    TESTING = "testing"
    SUPPORTED = "supported"
    REFUTED = "refuted"
    INCONCLUSIVE = "inconclusive"


class Hypothesis(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    statement: str  # testable hypothesis
    rationale: str
    supporting_evidence: list[str] = Field(default_factory=list)  # document IDs
    knowledge_graph_entities: list[str] = Field(default_factory=list)
    status: HypothesisStatus = HypothesisStatus.PROPOSED
    confidence: float = 0.0
    parent_hypothesis: str | None = None  # for refinement chains


class ExperimentType(str, Enum):
    DATA_ANALYSIS = "data_analysis"
    COMPUTATION = "computation"
    LITERATURE_REVIEW = "literature_review"
    API_QUERY = "api_query"
    COMPARISON = "comparison"


class Experiment(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    hypothesis_id: str
    experiment_type: ExperimentType
    description: str
    methodology: str  # step-by-step
    data_sources: list[str] = Field(default_factory=list)
    code: str = ""  # Python for computation type
    parameters: dict = Field(default_factory=dict)


class ExperimentResult(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    experiment_id: str
    raw_output: str = ""
    interpretation: str = ""
    supports_hypothesis: bool | None = None  # None = inconclusive
    confidence: float = 0.0
    artifacts: list[str] = Field(default_factory=list)
    citations: list[dict] = Field(default_factory=list)


class ResearchReport(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str
    research_question: str
    abstract: str = ""
    hypotheses: list[Hypothesis] = Field(default_factory=list)
    experiments: list[Experiment] = Field(default_factory=list)
    results: list[ExperimentResult] = Field(default_factory=list)
    conclusion: str = ""
    citations: list[dict] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    knowledge_graph_updates: list[dict] = Field(default_factory=list)


class ResearchCycleStatus(str, Enum):
    ACTIVE = "active"
    COMPLETED = "completed"
    ABANDONED = "abandoned"


class ResearchCycle(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    research_question: str
    max_iterations: int = 3
    current_iteration: int = 0
    hypotheses: list[Hypothesis] = Field(default_factory=list)
    experiments: list[Experiment] = Field(default_factory=list)
    results: list[ExperimentResult] = Field(default_factory=list)
    report: ResearchReport | None = None
    status: ResearchCycleStatus = ResearchCycleStatus.ACTIVE
