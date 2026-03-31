"""Data models for synthetic synesthesia brain-informed design analysis."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import List

import uuid

from pydantic import BaseModel, Field


class Modality(str, Enum):
    VISUAL = "visual"
    AUDIO = "audio"
    TEXT = "text"
    MULTIMODAL = "multimodal"


class BrainRegion(str, Enum):
    """Key brain regions relevant to design perception."""

    V1 = "v1_primary_visual"  # Edge detection, contrast
    V4 = "v4_color_form"  # Color processing, shape
    FFA = "fusiform_face_area"  # Face recognition
    PPA = "parahippocampal_place"  # Scene/layout recognition
    VWFA = "visual_word_form"  # Text/reading
    A1 = "a1_primary_auditory"  # Sound processing
    STG = "superior_temporal"  # Speech comprehension
    PFC = "prefrontal_cortex"  # Cognitive load, decision making
    AMG = "amygdala"  # Emotional response
    INS = "insula"  # Visceral/aesthetic feeling
    ACC = "anterior_cingulate"  # Conflict detection, error monitoring
    TPJ = "temporoparietal"  # Theory of mind, social cognition


class CorticalActivation(BaseModel):
    """Predicted activation level for a brain region."""

    region: BrainRegion
    activation: float  # 0.0 to 1.0
    interpretation: str  # What this means for design


class StimulusAnalysis(BaseModel):
    """Full analysis of a stimulus (image, audio, text, or multimodal)."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    modality: Modality
    stimulus_description: str
    activations: list[CorticalActivation] = Field(default_factory=list)
    attention_score: float = 0.0  # 0-1, how attention-grabbing
    cognitive_load: float = 0.0  # 0-1, how mentally taxing
    emotional_valence: float = 0.0  # -1 to 1, negative to positive
    emotional_arousal: float = 0.0  # 0-1, calm to exciting
    aesthetic_score: float = 0.0  # 0-1, overall aesthetic quality
    harmony_score: float = 0.0  # 0-1, cross-modal coherence
    analyzed_at: datetime = Field(default_factory=datetime.utcnow)


class DesignRecommendation(BaseModel):
    """Design recommendation based on brain response analysis."""

    category: str  # "color", "layout", "typography", "sound", "imagery", "cognitive_load"
    recommendation: str
    rationale: str  # Brain-science rationale
    brain_regions: list[BrainRegion] = Field(default_factory=list)
    confidence: float = 0.0
    priority: str = "medium"  # "high", "medium", "low"


class DesignReview(BaseModel):
    """Complete design review with brain-informed recommendations."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str
    analyses: list[StimulusAnalysis] = Field(default_factory=list)
    recommendations: list[DesignRecommendation] = Field(default_factory=list)
    overall_score: float = 0.0  # 0-100
    summary: str = ""
    generated_at: datetime = Field(default_factory=datetime.utcnow)


class ColorProfile(BaseModel):
    """Color analysis with brain-response predictions."""

    hex_colors: list[str]
    dominant_wavelengths: list[float] = Field(default_factory=list)  # nm
    warm_cool_ratio: float = 0.5  # 0=all cool, 1=all warm
    contrast_ratio: float = 0.0
    v4_activation: float = 0.0  # Color processing region
    emotional_associations: list[str] = Field(default_factory=list)
