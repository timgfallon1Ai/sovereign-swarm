"""Data models for the Strategic Intelligence agent."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class GapClassification(str, Enum):
    BLIND_SPOT = "blind_spot"  # external signal exists, internal unaware
    CONFIRMED = "confirmed"  # external aligns with internal assumptions
    OPPORTUNITY = "opportunity"  # external suggests untapped potential
    THREAT = "threat"  # external contradicts internal position


class GapSeverity(str, Enum):
    CRITICAL = "critical"  # 0.8-1.0
    HIGH = "high"  # 0.6-0.8
    MEDIUM = "medium"  # 0.4-0.6
    LOW = "low"  # 0.2-0.4
    INFO = "info"  # 0.0-0.2


class FrameworkTier(str, Enum):
    AUTOMATED = "tier_1"  # weekly auto-run
    ON_DEMAND = "tier_2"  # triggered by signal or user


# ---------------------------------------------------------------------------
# External sensing
# ---------------------------------------------------------------------------


class ExternalSignal(BaseModel):
    source_url: str = ""
    source_type: str = ""  # "web_search", "news", "social", "market_data"
    query_used: str = ""
    raw_content: str = ""  # truncated to 2000 chars
    extracted_facts: list[str] = Field(default_factory=list)
    fetched_at: datetime = Field(default_factory=datetime.utcnow)
    relevance_score: float = 0.0


# ---------------------------------------------------------------------------
# Internal mirroring
# ---------------------------------------------------------------------------


class InternalSnapshot(BaseModel):
    tenant: str
    brand_profile: dict[str, Any] = Field(default_factory=dict)
    kb_excerpts: list[dict[str, Any]] = Field(default_factory=list)
    financial_summary: dict[str, Any] = Field(default_factory=dict)
    current_assumptions: list[str] = Field(default_factory=list)
    snapshot_at: datetime = Field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# Gap detection
# ---------------------------------------------------------------------------


class Gap(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    framework: str
    classification: GapClassification
    severity: float = 0.5
    severity_label: GapSeverity = GapSeverity.MEDIUM
    external_evidence: list[str] = Field(default_factory=list)
    internal_state: str = ""
    description: str = ""
    recommendation: str = ""


# ---------------------------------------------------------------------------
# Framework results
# ---------------------------------------------------------------------------


class FrameworkResult(BaseModel):
    framework_name: str
    tenant: str
    tier: FrameworkTier
    external_signals: list[ExternalSignal] = Field(default_factory=list)
    synthesis: dict[str, Any] = Field(default_factory=dict)
    gaps: list[Gap] = Field(default_factory=list)
    run_at: datetime = Field(default_factory=datetime.utcnow)
    tokens_used: int = 0
    cost_usd: float = 0.0


# ---------------------------------------------------------------------------
# Briefing
# ---------------------------------------------------------------------------


class WeeklyBriefing(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    tenant: str
    week_of: str = ""  # "2026-W15"
    framework_results: list[FrameworkResult] = Field(default_factory=list)
    top_gaps: list[Gap] = Field(default_factory=list)
    deltas_from_prior: list[dict[str, Any]] = Field(default_factory=list)
    recommendations: list[dict[str, Any]] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    total_cost_usd: float = 0.0


# ---------------------------------------------------------------------------
# Learning loop
# ---------------------------------------------------------------------------


class RecommendationOutcome(BaseModel):
    recommendation_id: str = ""
    gap_id: str = ""
    acted_on: bool = False
    outcome: str = ""  # "implemented", "rejected", "deferred"
    feedback: str = ""
    recorded_at: datetime = Field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# Framework-specific output schemas
# ---------------------------------------------------------------------------


class MarketEstimate(BaseModel):
    estimate: str = ""
    source: str = ""
    rationale: str = ""
    confidence: str = "medium"


class DemandTrend(BaseModel):
    trend: str
    direction: str = ""  # growing, declining, emerging
    evidence: str = ""


class UnderservedOpportunity(BaseModel):
    segment: str
    gap: str = ""
    potential: str = ""


class CapitalFlow(BaseModel):
    event: str
    amount: str = ""
    relevance: str = ""


class MarketBreakdownOutput(BaseModel):
    tam: MarketEstimate = Field(default_factory=MarketEstimate)
    sam: MarketEstimate = Field(default_factory=MarketEstimate)
    som: MarketEstimate = Field(default_factory=MarketEstimate)
    demand_trends: list[DemandTrend] = Field(default_factory=list)
    underserved_opportunities: list[UnderservedOpportunity] = Field(default_factory=list)
    capital_flows: list[CapitalFlow] = Field(default_factory=list)


class ScoredProblem(BaseModel):
    problem: str
    urgency: int = 5  # 1-10
    willingness_to_pay: int = 5  # 1-10
    growth_trajectory: str = "stable"  # rising_fast, stable, declining
    complaint_signal: bool = False
    combined_score: int = 10
    rationale: str = ""


class ProblemPriorityOutput(BaseModel):
    problems: list[ScoredProblem] = Field(default_factory=list)


class CompetitorProfile(BaseModel):
    name: str
    url: str = ""
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    ignored_audiences: list[str] = Field(default_factory=list)
    gap_analysis: str = ""
    positioning_angle: str = ""


class CompetitorMapOutput(BaseModel):
    competitors: list[CompetitorProfile] = Field(default_factory=list)
    positioning_statement: str = ""
    key_differentiators: list[str] = Field(default_factory=list)
    biggest_vulnerability: str = ""


class ContentHook(BaseModel):
    hook: str
    emotional_trigger: str = ""  # fomo, social_status, curiosity, controversy


class ContentFormatEntry(BaseModel):
    format: str
    platform: str
    ideal_length: str = ""
    why_it_spreads: str = ""
    example_title: str = ""


class ContentEngineOutput(BaseModel):
    hooks: list[ContentHook] = Field(default_factory=list)
    format_matrix: list[ContentFormatEntry] = Field(default_factory=list)
    shareability_audit: list[dict[str, str]] = Field(default_factory=list)
    weekly_system: dict[str, Any] = Field(default_factory=dict)


class ChannelRecommendation(BaseModel):
    channel: str
    format: str = ""
    cost_efficiency_rank: int = 0
    rationale: str = ""


class DistributionPlanOutput(BaseModel):
    top_channels: list[ChannelRecommendation] = Field(default_factory=list)
    weekly_calendar: dict[str, list[str]] = Field(default_factory=dict)  # week1..week4
    organic_paid_split: dict[str, Any] = Field(default_factory=dict)
    leverage_plays: list[str] = Field(default_factory=list)


class OfferSection(BaseModel):
    headline: str = ""
    icp: str = ""
    value_proposition: str = ""
    offer_components: list[str] = Field(default_factory=list)
    pricing_tiers: list[dict[str, str]] = Field(default_factory=list)
    guarantee: str = ""
    competitive_edge: list[str] = Field(default_factory=list)


class OfferCreationOutput(BaseModel):
    offer: OfferSection = Field(default_factory=OfferSection)


class ScalePhase(BaseModel):
    name: str
    months: str = ""
    actions: list[str] = Field(default_factory=list)
    bottlenecks: list[str] = Field(default_factory=list)
    leading_metric: str = ""


class ScaleSystemOutput(BaseModel):
    phases: list[ScalePhase] = Field(default_factory=list)
    target_revenue: str = ""
    timeframe: str = ""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def severity_label(score: float) -> GapSeverity:
    if score >= 0.8:
        return GapSeverity.CRITICAL
    if score >= 0.6:
        return GapSeverity.HIGH
    if score >= 0.4:
        return GapSeverity.MEDIUM
    if score >= 0.2:
        return GapSeverity.LOW
    return GapSeverity.INFO
