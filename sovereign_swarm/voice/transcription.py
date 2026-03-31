"""Transcription engine wrapping Whisper API.

Phase A: API-based transcription via OpenAI's Whisper endpoint.
Phase B: on-device Whisper via MLX for local processing.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import structlog

from sovereign_swarm.voice.models import TranscriptionResult, TranscriptionSegment

logger = structlog.get_logger()


class TranscriptionEngine:
    """Speech-to-text transcription engine.

    Phase A: wraps the OpenAI Whisper API via httpx.
    Phase B: will use on-device Whisper via MLX for local, private transcription.
    """

    def __init__(self, api_key: str = "", base_url: str = "") -> None:
        self._api_key = api_key
        self._base_url = base_url or "https://api.openai.com/v1"
        self._client = None

    async def transcribe(
        self,
        audio_path: str | Path,
        language: str = "en",
        model: str = "whisper-1",
    ) -> TranscriptionResult:
        """Transcribe an audio file to text.

        Args:
            audio_path: Path to audio file (mp3, wav, m4a, etc.)
            language: ISO language code
            model: Whisper model to use

        Returns:
            TranscriptionResult with text, confidence, and segments.
        """
        audio_path = Path(audio_path)
        if not audio_path.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        if self._api_key:
            return await self._transcribe_api(audio_path, language, model)

        logger.warning(
            "transcription.no_api_key",
            message="No API key configured; returning stub result",
        )
        return TranscriptionResult(
            text=f"[Transcription stub -- configure API key for {audio_path.name}]",
            confidence=0.0,
            language=language,
            metadata={"source": str(audio_path), "engine": "stub"},
        )

    async def _transcribe_api(
        self, audio_path: Path, language: str, model: str
    ) -> TranscriptionResult:
        """Transcribe using OpenAI Whisper API."""
        client = self._get_client()

        try:
            with open(audio_path, "rb") as f:
                response = await client.post(
                    f"{self._base_url}/audio/transcriptions",
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    files={"file": (audio_path.name, f)},
                    data={
                        "model": model,
                        "language": language,
                        "response_format": "verbose_json",
                        "timestamp_granularities[]": "segment",
                    },
                    timeout=60.0,
                )
                response.raise_for_status()
                data = response.json()

            # Parse segments if available
            segments = []
            for seg in data.get("segments", []):
                segments.append(
                    TranscriptionSegment(
                        text=seg.get("text", ""),
                        start_seconds=seg.get("start", 0.0),
                        end_seconds=seg.get("end", 0.0),
                        confidence=seg.get("avg_logprob", 0.0),
                    )
                )

            return TranscriptionResult(
                text=data.get("text", ""),
                confidence=0.9,  # Whisper doesn't return overall confidence
                language=data.get("language", language),
                duration_seconds=data.get("duration", 0.0),
                segments=segments,
                metadata={"model": model, "engine": "whisper_api"},
            )

        except Exception as e:
            logger.error("transcription.api_failed", error=str(e))
            return TranscriptionResult(
                text=f"[Transcription failed: {e}]",
                confidence=0.0,
                language=language,
                metadata={"error": str(e), "engine": "whisper_api"},
            )

    def _get_client(self):
        if self._client is None:
            try:
                import httpx

                self._client = httpx.AsyncClient()
            except ImportError:
                raise RuntimeError("httpx is required for API-based transcription")
        return self._client
