"""Emotion detection from text using heuristic keyword analysis.

Maps detected emotions to the valence-arousal-dominance (VAD) model
for use in modulating voice synthesis and the Orb's visual state.
"""

from __future__ import annotations

import re
from typing import Any

import structlog

from sovereign_swarm.voice.models import Emotion, EmotionProfile

logger = structlog.get_logger()

# ------------------------------------------------------------------
# Emotion keyword lexicon
# ------------------------------------------------------------------

_EMOTION_KEYWORDS: dict[Emotion, list[str]] = {
    Emotion.JOY: [
        "happy", "glad", "joy", "joyful", "excited", "thrilled", "delighted",
        "wonderful", "fantastic", "amazing", "great", "love", "loving",
        "cheerful", "elated", "ecstatic", "bliss", "grateful", "thankful",
        "celebration", "celebrate", "congrats", "congratulations", "awesome",
        "brilliant", "excellent", "superb", "magnificent",
    ],
    Emotion.ANGER: [
        "angry", "furious", "rage", "mad", "frustrated", "irritated",
        "annoyed", "outraged", "livid", "hostile", "bitter", "resentful",
        "hate", "hatred", "disgusted", "infuriated", "aggravated",
        "enraged", "irate", "fuming",
    ],
    Emotion.SADNESS: [
        "sad", "depressed", "unhappy", "miserable", "grief", "sorrow",
        "heartbroken", "devastated", "disappointed", "lonely", "hopeless",
        "gloomy", "melancholy", "mourning", "crying", "tears", "loss",
        "regret", "despair", "downcast",
    ],
    Emotion.FEAR: [
        "afraid", "scared", "fearful", "terrified", "anxious", "worried",
        "nervous", "panic", "dread", "horror", "frightened", "alarmed",
        "apprehensive", "uneasy", "tense", "phobia", "threat",
        "intimidated", "vulnerable",
    ],
    Emotion.SURPRISE: [
        "surprised", "shocked", "amazed", "astonished", "stunned",
        "unexpected", "unbelievable", "incredible", "wow", "whoa",
        "startled", "bewildered", "awestruck", "speechless",
    ],
    Emotion.TRUST: [
        "trust", "confident", "reliable", "safe", "secure", "faithful",
        "loyal", "honest", "dependable", "supportive", "committed",
        "believe", "faith", "certain", "assured",
    ],
    Emotion.DISGUST: [
        "disgusting", "revolting", "repulsive", "gross", "nasty",
        "horrible", "awful", "sickening", "vile", "repugnant",
        "loathsome", "abhorrent",
    ],
    Emotion.ANTICIPATION: [
        "anticipate", "expect", "looking forward", "eager", "hopeful",
        "optimistic", "curious", "interested", "planning", "preparing",
        "upcoming", "soon", "can't wait", "excited about",
    ],
}

# VAD mappings for each emotion
_EMOTION_VAD: dict[Emotion, tuple[float, float, float]] = {
    Emotion.JOY: (0.8, 0.6, 0.6),
    Emotion.ANGER: (-0.6, 0.8, 0.7),
    Emotion.SADNESS: (-0.7, -0.4, -0.5),
    Emotion.FEAR: (-0.7, 0.6, -0.6),
    Emotion.SURPRISE: (0.2, 0.7, -0.1),
    Emotion.TRUST: (0.6, -0.1, 0.3),
    Emotion.DISGUST: (-0.6, 0.3, 0.2),
    Emotion.ANTICIPATION: (0.4, 0.4, 0.2),
    Emotion.NEUTRAL: (0.0, 0.0, 0.0),
}


class EmotionDetector:
    """Analyzes text for emotional content using keyword-based detection.

    Maps detected emotions to the valence-arousal-dominance (VAD) model.
    Used to modulate voice synthesis parameters and the Orb's visual state.
    """

    def detect(self, text: str) -> EmotionProfile:
        """Detect emotions in text and return an EmotionProfile."""
        text_lower = text.lower()
        words = set(re.findall(r"\b[a-z]+\b", text_lower))

        # Score each emotion
        scores: dict[str, float] = {}
        for emotion, keywords in _EMOTION_KEYWORDS.items():
            # Check both single words and multi-word phrases
            word_matches = sum(1 for kw in keywords if kw in words)
            phrase_matches = sum(
                1 for kw in keywords if " " in kw and kw in text_lower
            )
            score = word_matches + phrase_matches * 1.5
            scores[emotion.value] = score

        # Normalize scores
        total = sum(scores.values())
        if total > 0:
            scores = {k: v / total for k, v in scores.items()}

        # Find dominant emotion
        if total == 0:
            dominant = Emotion.NEUTRAL
            confidence = 1.0
        else:
            dominant_key = max(scores, key=lambda k: scores[k])
            dominant = Emotion(dominant_key)
            confidence = min(scores[dominant_key] * 2, 1.0)  # Scale up, cap at 1.0

        # Get VAD values for dominant emotion
        vad = _EMOTION_VAD.get(dominant, (0.0, 0.0, 0.0))

        return EmotionProfile(
            valence=vad[0],
            arousal=vad[1],
            dominance=vad[2],
            detected_emotion=dominant,
            confidence=round(confidence, 3),
            emotion_scores=scores,
        )

    def detect_multiple(self, texts: list[str]) -> EmotionProfile:
        """Detect aggregate emotion across multiple texts."""
        if not texts:
            return EmotionProfile()

        combined = " ".join(texts)
        return self.detect(combined)

    def format_profile_markdown(self, profile: EmotionProfile) -> str:
        """Format an emotion profile as markdown."""
        lines = [
            "## Emotion Analysis\n",
            f"**Detected Emotion:** {profile.detected_emotion.value.title()}",
            f"**Confidence:** {profile.confidence:.0%}\n",
            "### VAD Model\n",
            f"- **Valence:** {profile.valence:+.2f} "
            f"({'positive' if profile.valence > 0 else 'negative' if profile.valence < 0 else 'neutral'})",
            f"- **Arousal:** {profile.arousal:+.2f} "
            f"({'excited' if profile.arousal > 0 else 'calm' if profile.arousal < 0 else 'neutral'})",
            f"- **Dominance:** {profile.dominance:+.2f} "
            f"({'dominant' if profile.dominance > 0 else 'submissive' if profile.dominance < 0 else 'neutral'})",
            "",
        ]

        # Top emotions
        if profile.emotion_scores:
            sorted_emotions = sorted(
                profile.emotion_scores.items(), key=lambda x: -x[1]
            )[:5]
            if sorted_emotions:
                lines.append("### Emotion Breakdown\n")
                lines.append("| Emotion | Score |")
                lines.append("|---------|-------|")
                for emo, score in sorted_emotions:
                    bar = "#" * int(score * 20)
                    lines.append(f"| {emo.title()} | {score:.1%} {bar} |")

        return "\n".join(lines)
