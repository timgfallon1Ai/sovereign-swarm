"""Data models for the Voice agent (The Orb Engine)."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class Emotion(str, Enum):
    JOY = "joy"
    ANGER = "anger"
    SADNESS = "sadness"
    FEAR = "fear"
    SURPRISE = "surprise"
    TRUST = "trust"
    DISGUST = "disgust"
    ANTICIPATION = "anticipation"
    NEUTRAL = "neutral"


class OutputFormat(str, Enum):
    WAV = "wav"
    MP3 = "mp3"
    OGG = "ogg"
    FLAC = "flac"


class TranscriptionSegment(BaseModel):
    """A time-aligned segment of a transcription."""

    text: str
    start_seconds: float = 0.0
    end_seconds: float = 0.0
    confidence: float = 0.0


class VoiceConfig(BaseModel):
    """Configuration for voice synthesis."""

    language: str = "en"
    speed: float = 1.0  # 0.5 to 2.0
    pitch: float = 1.0  # 0.5 to 2.0
    emotion: Emotion = Emotion.NEUTRAL
    voice_id: str = ""  # specific voice selection


class TranscriptionResult(BaseModel):
    """Result from speech-to-text transcription."""

    text: str
    confidence: float = 0.0
    language: str = "en"
    duration_seconds: float = 0.0
    segments: list[TranscriptionSegment] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)


class SpeechSynthesisRequest(BaseModel):
    """A request to synthesize speech from text."""

    text: str
    voice_config: VoiceConfig = Field(default_factory=VoiceConfig)
    output_format: OutputFormat = OutputFormat.WAV


class EmotionProfile(BaseModel):
    """Emotion analysis result using the valence-arousal-dominance model."""

    valence: float = 0.0  # -1.0 (negative) to 1.0 (positive)
    arousal: float = 0.0  # -1.0 (calm) to 1.0 (excited)
    dominance: float = 0.0  # -1.0 (submissive) to 1.0 (dominant)
    detected_emotion: Emotion = Emotion.NEUTRAL
    confidence: float = 0.0
    emotion_scores: dict[str, float] = Field(default_factory=dict)  # emotion -> score
