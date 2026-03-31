"""Data models for the Competitive Intelligence agent."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class ChangeType(str, Enum):
    PRICING = "pricing"
    FEATURE = "feature"
    CONTENT = "content"
    DESIGN = "design"
    SEO = "seo"
    SOCIAL = "social"
    OTHER = "other"


class MarketTrend(str, Enum):
    GROWING = "growing"
    STABLE = "stable"
    DECLINING = "declining"
    EMERGING = "emerging"


class Competitor(BaseModel):
    """A tracked competitor."""

    id: str = ""
    name: str
    url: str = ""
    description: str = ""
    products: list[str] = Field(default_factory=list)
    pricing: dict[str, str] = Field(default_factory=dict)  # plan_name -> price
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    last_analyzed: datetime | None = None
    metadata: dict = Field(default_factory=dict)


class CompetitorChange(BaseModel):
    """A detected change at a competitor."""

    competitor_id: str
    competitor_name: str = ""
    change_type: ChangeType
    old_value: str = ""
    new_value: str = ""
    detected_at: datetime = Field(default_factory=lambda: datetime.now())
    significance: str = "medium"  # low, medium, high
    notes: str = ""


class MarketPosition(BaseModel):
    """Market positioning data."""

    market: str
    our_position: str = ""
    competitors: list[str] = Field(default_factory=list)
    market_size: str = ""
    trend: MarketTrend = MarketTrend.STABLE
    our_share_estimate: str = ""
    notes: str = ""


class SentimentReport(BaseModel):
    """Sentiment analysis from a source."""

    source: str  # e.g., "twitter", "reddit", "reviews"
    competitor_name: str = ""
    sentiment_score: float = 0.0  # -1.0 to 1.0
    sample_size: int = 0
    themes: list[str] = Field(default_factory=list)
    analyzed_at: datetime = Field(default_factory=lambda: datetime.now())
