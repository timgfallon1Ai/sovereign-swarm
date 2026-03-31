"""VoiceAgent -- The Orb Engine for the swarm."""

from __future__ import annotations

from typing import Any

import structlog

from sovereign_swarm.voice.models import (
    Emotion,
    EmotionProfile,
    OutputFormat,
    VoiceConfig,
)
from sovereign_swarm.protocol.swarm_agent import (
    SwarmAgent,
    SwarmAgentCard,
    SwarmAgentRequest,
    SwarmAgentResponse,
)

logger = structlog.get_logger()


class VoiceAgent(SwarmAgent):
    """Voice agent (The Orb Engine).

    Handles speech-to-text transcription, text-to-speech synthesis,
    emotion detection in text, and voice command parsing. Drives the
    Orb's visual state based on detected emotional content.
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._config = config or {}
        self._transcription = None
        self._synthesizer = None
        self._emotion = None

    @property
    def card(self) -> SwarmAgentCard:
        return SwarmAgentCard(
            name="VoiceAgent",
            description=(
                "Voice agent (The Orb Engine) -- speech-to-text, text-to-speech, "
                "emotion detection, and voice command parsing. Drives the Orb's "
                "visual state through emotional content analysis."
            ),
            version="0.1.0",
            domains=["voice", "speech", "audio", "transcription", "tts"],
            supported_intents=[
                "transcribe",
                "synthesize",
                "detect_emotion",
                "voice_command",
            ],
            capabilities=[
                "transcribe",
                "synthesize",
                "detect_emotion",
                "voice_command",
            ],
        )

    # ------------------------------------------------------------------
    # Core execute
    # ------------------------------------------------------------------

    async def execute(self, request: SwarmAgentRequest) -> SwarmAgentResponse:
        """Route a voice task to the appropriate handler."""
        task = request.task.lower()
        params = request.parameters or request.context or {}

        try:
            if any(kw in task for kw in ("transcribe", "speech to text", "stt", "listen")):
                result = await self._handle_transcribe(params)
            elif any(kw in task for kw in ("speak", "say", "synthesize", "tts", "read aloud")):
                result = await self._handle_synthesize(params)
            elif any(kw in task for kw in ("emotion", "sentiment", "feeling", "mood")):
                result = await self._handle_emotion(params)
            elif any(kw in task for kw in ("command", "parse", "intent")):
                result = await self._handle_voice_command(params)
            else:
                # Default: try emotion detection on the task text itself
                result = await self._handle_emotion({"text": request.task})

            return SwarmAgentResponse(
                agent_name=self.card.name,
                status="success",
                output=result.get("markdown", str(result)),
                data=result,
                confidence=result.get("confidence", 0.7),
            )
        except Exception as e:
            logger.error("voice.execute_failed", error=str(e))
            return SwarmAgentResponse(
                agent_name=self.card.name,
                status="error",
                error=str(e),
            )

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------

    async def _handle_transcribe(self, params: dict) -> dict:
        """Transcribe audio to text."""
        engine = self._get_transcription()
        audio_path = params.get("audio_path", params.get("file", ""))
        language = params.get("language", "en")

        if not audio_path:
            return {
                "markdown": "## Transcription\n\nNo audio file path provided.",
                "confidence": 0.5,
            }

        result = await engine.transcribe(audio_path, language)

        md = "## Transcription Result\n\n"
        md += f"**Text:** {result.text}\n\n"
        md += f"**Language:** {result.language}\n"
        md += f"**Duration:** {result.duration_seconds:.1f}s\n"
        md += f"**Confidence:** {result.confidence:.0%}\n"

        if result.segments:
            md += "\n### Segments\n\n"
            md += "| Time | Text |\n"
            md += "|------|------|\n"
            for seg in result.segments:
                md += (
                    f"| {seg.start_seconds:.1f}s - {seg.end_seconds:.1f}s "
                    f"| {seg.text.strip()} |\n"
                )

        # Also detect emotion in transcribed text
        detector = self._get_emotion_detector()
        emotion = detector.detect(result.text)

        md += f"\n**Detected Emotion:** {emotion.detected_emotion.value.title()} "
        md += f"(confidence: {emotion.confidence:.0%})\n"

        return {
            "markdown": md,
            "text": result.text,
            "duration": result.duration_seconds,
            "emotion": emotion.detected_emotion.value,
            "orb_state": self._emotion_to_orb_state(emotion),
            "confidence": result.confidence,
        }

    async def _handle_synthesize(self, params: dict) -> dict:
        """Synthesize text to speech."""
        synth = self._get_synthesizer()
        text = params.get("text", "")

        if not text:
            return {
                "markdown": "## Speech Synthesis\n\nNo text provided to synthesize.",
                "confidence": 0.5,
            }

        # Parse voice config from params
        config = VoiceConfig(
            language=params.get("language", "en"),
            speed=params.get("speed", 1.0),
            pitch=params.get("pitch", 1.0),
            emotion=Emotion(params.get("emotion", "neutral")),
            voice_id=params.get("voice_id", ""),
        )

        output_format = OutputFormat(params.get("format", "wav"))
        audio_bytes = await synth.synthesize(text, config, output_format)

        md = "## Speech Synthesis\n\n"
        md += f"**Text:** {text[:200]}{'...' if len(text) > 200 else ''}\n"
        md += f"**Voice:** {config.voice_id or 'default'}\n"
        md += f"**Emotion:** {config.emotion.value}\n"
        md += f"**Speed:** {config.speed}x\n"
        md += f"**Format:** {output_format.value}\n"
        md += f"**Audio size:** {len(audio_bytes):,} bytes\n"

        return {
            "markdown": md,
            "audio_bytes_length": len(audio_bytes),
            "format": output_format.value,
            "orb_state": self._emotion_to_orb_state(
                EmotionProfile(detected_emotion=config.emotion)
            ),
            "confidence": 0.8,
        }

    async def _handle_emotion(self, params: dict) -> dict:
        """Detect emotion in text."""
        detector = self._get_emotion_detector()
        text = params.get("text", "")

        if not text:
            return {
                "markdown": "## Emotion Detection\n\nNo text provided for analysis.",
                "confidence": 0.5,
            }

        profile = detector.detect(text)
        md = detector.format_profile_markdown(profile)

        # Add Orb state mapping
        orb_state = self._emotion_to_orb_state(profile)
        md += f"\n### Orb Visual State\n"
        md += f"- **Color:** {orb_state['color']}\n"
        md += f"- **Pulse Rate:** {orb_state['pulse_rate']}\n"
        md += f"- **Intensity:** {orb_state['intensity']}\n"

        return {
            "markdown": md,
            "emotion": profile.detected_emotion.value,
            "confidence": profile.confidence,
            "vad": {
                "valence": profile.valence,
                "arousal": profile.arousal,
                "dominance": profile.dominance,
            },
            "orb_state": orb_state,
        }

    async def _handle_voice_command(self, params: dict) -> dict:
        """Parse a voice command into structured intent."""
        text = params.get("text", params.get("command", ""))

        if not text:
            return {
                "markdown": "## Voice Command\n\nNo command text provided.",
                "confidence": 0.5,
            }

        intent = self._parse_intent(text)

        md = "## Voice Command Parsed\n\n"
        md += f"**Input:** \"{text}\"\n"
        md += f"**Intent:** {intent['intent']}\n"
        md += f"**Confidence:** {intent['confidence']:.0%}\n"
        if intent.get("entities"):
            md += "\n### Entities\n"
            for key, val in intent["entities"].items():
                md += f"- **{key}:** {val}\n"

        return {
            "markdown": md,
            "intent": intent["intent"],
            "entities": intent.get("entities", {}),
            "confidence": intent["confidence"],
        }

    # ------------------------------------------------------------------
    # Orb state mapping
    # ------------------------------------------------------------------

    @staticmethod
    def _emotion_to_orb_state(profile: EmotionProfile) -> dict[str, Any]:
        """Map an emotion profile to Orb visual parameters.

        The Orb's visual state is driven by:
        - Color: mapped from emotion type
        - Pulse rate: derived from arousal
        - Intensity: derived from valence magnitude
        """
        color_map = {
            Emotion.JOY: "#FFD700",  # gold
            Emotion.ANGER: "#FF4444",  # red
            Emotion.SADNESS: "#4488FF",  # blue
            Emotion.FEAR: "#9944FF",  # purple
            Emotion.SURPRISE: "#FF8800",  # orange
            Emotion.TRUST: "#44CC88",  # green
            Emotion.DISGUST: "#886644",  # brown
            Emotion.ANTICIPATION: "#FFAA44",  # amber
            Emotion.NEUTRAL: "#88AACC",  # cool gray-blue
        }

        color = color_map.get(profile.detected_emotion, "#88AACC")
        # Pulse rate: higher arousal = faster pulse (0.5-3.0 Hz)
        pulse_rate = round(1.0 + profile.arousal * 1.0, 2)
        # Intensity: higher absolute valence = brighter
        intensity = round(0.5 + abs(profile.valence) * 0.5, 2)

        return {
            "color": color,
            "pulse_rate": max(0.5, min(3.0, pulse_rate)),
            "intensity": max(0.3, min(1.0, intensity)),
            "emotion": profile.detected_emotion.value,
        }

    # ------------------------------------------------------------------
    # Intent parsing (simple keyword-based, Phase A)
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_intent(text: str) -> dict[str, Any]:
        """Parse voice command text into structured intent."""
        text_lower = text.lower().strip()

        # Command patterns
        patterns: list[tuple[list[str], str]] = [
            (["play", "music", "song"], "play_media"),
            (["stop", "pause", "halt"], "stop"),
            (["set timer", "alarm", "remind"], "set_reminder"),
            (["weather", "forecast", "temperature"], "get_weather"),
            (["what time", "current time", "clock"], "get_time"),
            (["search", "find", "look up", "google"], "search"),
            (["send", "message", "text", "email"], "send_message"),
            (["call", "phone", "dial"], "make_call"),
            (["open", "launch", "start"], "open_app"),
            (["turn on", "turn off", "toggle"], "smart_home"),
            (["how much", "balance", "net worth"], "finance_query"),
            (["schedule", "meeting", "calendar"], "calendar"),
            (["note", "remember", "save"], "take_note"),
        ]

        best_intent = "unknown"
        best_score = 0
        entities: dict[str, str] = {}

        for keywords, intent in patterns:
            score = sum(1 for kw in keywords if kw in text_lower)
            if score > best_score:
                best_score = score
                best_intent = intent

        # Extract simple entities
        # Time-related
        import re

        time_match = re.search(r"(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)", text_lower)
        if time_match:
            entities["time"] = time_match.group(1)

        # Numbers
        num_match = re.search(r"\b(\d+)\b", text_lower)
        if num_match and "time" not in entities:
            entities["number"] = num_match.group(1)

        confidence = min(best_score * 0.3 + 0.2, 0.95) if best_score > 0 else 0.1

        return {
            "intent": best_intent,
            "confidence": confidence,
            "entities": entities,
            "raw_text": text,
        }

    # ------------------------------------------------------------------
    # Lazy init
    # ------------------------------------------------------------------

    def _get_transcription(self):
        if self._transcription is None:
            from sovereign_swarm.voice.transcription import TranscriptionEngine

            api_key = self._config.get("openai_api_key", "")
            self._transcription = TranscriptionEngine(api_key=api_key)
        return self._transcription

    def _get_synthesizer(self):
        if self._synthesizer is None:
            from sovereign_swarm.voice.synthesis import SpeechSynthesizer

            api_key = self._config.get("openai_api_key", "")
            provider = "openai" if api_key else "stub"
            self._synthesizer = SpeechSynthesizer(api_key=api_key, provider=provider)
        return self._synthesizer

    def _get_emotion_detector(self):
        if self._emotion is None:
            from sovereign_swarm.voice.emotion import EmotionDetector

            self._emotion = EmotionDetector()
        return self._emotion
