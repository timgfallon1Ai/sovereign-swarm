"""Specialized color analysis with brain-response predictions.

Maps hex colors to wavelength -> retinal response -> V4 cortical processing ->
emotional association.
"""

from __future__ import annotations

from sovereign_swarm.synesthesia.models import ColorProfile


class ColorEngine:
    """Analyzes color palettes using neuroscience-informed color perception models.

    Maps hex colors to wavelength -> retinal response -> V4 cortical processing ->
    emotional association.
    """

    # Color-emotion associations based on neuroscience literature
    COLOR_EMOTIONS: dict[str, dict] = {
        "red": {
            "valence": 0.2,
            "arousal": 0.9,
            "associations": ["energy", "urgency", "passion", "danger"],
        },
        "orange": {
            "valence": 0.6,
            "arousal": 0.7,
            "associations": ["warmth", "enthusiasm", "creativity", "friendliness"],
        },
        "yellow": {
            "valence": 0.7,
            "arousal": 0.6,
            "associations": ["optimism", "attention", "caution", "happiness"],
        },
        "green": {
            "valence": 0.6,
            "arousal": 0.3,
            "associations": ["nature", "growth", "safety", "freshness"],
        },
        "blue": {
            "valence": 0.5,
            "arousal": 0.2,
            "associations": ["trust", "calm", "professionalism", "reliability"],
        },
        "purple": {
            "valence": 0.4,
            "arousal": 0.4,
            "associations": ["luxury", "creativity", "mystery", "wisdom"],
        },
        "pink": {
            "valence": 0.7,
            "arousal": 0.3,
            "associations": ["softness", "nurturing", "playfulness", "romance"],
        },
        "black": {
            "valence": 0.2,
            "arousal": 0.4,
            "associations": ["power", "elegance", "sophistication", "authority"],
        },
        "white": {
            "valence": 0.6,
            "arousal": 0.1,
            "associations": ["purity", "simplicity", "space", "clarity"],
        },
        "gray": {
            "valence": 0.3,
            "arousal": 0.1,
            "associations": ["neutral", "balance", "professional", "subdued"],
        },
    }

    def analyze_palette(self, hex_colors: list[str]) -> ColorProfile:
        """Analyze a color palette for brain-response predictions."""
        # Parse hex colors to RGB
        rgbs = [self._hex_to_rgb(c) for c in hex_colors]

        # Classify each color
        color_names = [self._classify_color(rgb) for rgb in rgbs]

        # Warm/cool ratio
        warm = sum(
            1 for name in color_names if name in ["red", "orange", "yellow", "pink"]
        )
        cool = sum(
            1 for name in color_names if name in ["blue", "green", "purple"]
        )
        total = max(warm + cool, 1)

        # Contrast ratio (simplified: max luminance difference)
        luminances = [0.299 * r + 0.587 * g + 0.114 * b for r, g, b in rgbs]
        contrast = (
            (max(luminances) - min(luminances)) / 255.0 if luminances else 0
        )

        # V4 activation prediction
        color_variety = len(set(color_names))
        v4_activation = min(1.0, color_variety / 5 * 0.6 + contrast * 0.4)

        # Emotional associations
        all_associations: list[str] = []
        for name in set(color_names):
            if name in self.COLOR_EMOTIONS:
                all_associations.extend(self.COLOR_EMOTIONS[name]["associations"][:2])

        return ColorProfile(
            hex_colors=hex_colors,
            warm_cool_ratio=warm / total,
            contrast_ratio=round(contrast, 2),
            v4_activation=round(v4_activation, 2),
            emotional_associations=list(set(all_associations))[:8],
        )

    def score_palette_harmony(self, hex_colors: list[str]) -> dict:
        """Score color harmony using color theory relationships."""
        if len(hex_colors) < 2:
            return {"harmony_type": "monochromatic", "score": 1.0}

        hues = [self._rgb_to_hue(self._hex_to_rgb(c)) for c in hex_colors]

        # Check for common harmony types
        if self._is_complementary(hues):
            return {
                "harmony_type": "complementary",
                "score": 0.8,
                "brain_note": "Strong V4 activation from opponent-process color pairs",
            }
        elif self._is_analogous(hues):
            return {
                "harmony_type": "analogous",
                "score": 0.9,
                "brain_note": "Smooth V4 processing — adjacent hues create visual flow",
            }
        elif self._is_triadic(hues):
            return {
                "harmony_type": "triadic",
                "score": 0.7,
                "brain_note": "Balanced but energetic — V4 works harder to process three distinct hue families",
            }
        else:
            # Calculate harmony from hue distribution
            hue_spread = max(hues) - min(hues) if hues else 0
            score = 0.5 + (1 - abs(hue_spread - 180) / 180) * 0.3
            return {"harmony_type": "custom", "score": round(score, 2)}

    def predict_emotional_response(self, hex_colors: list[str]) -> dict:
        """Predict emotional response to a color palette."""
        color_names = [self._classify_color(self._hex_to_rgb(c)) for c in hex_colors]

        total_valence = 0.0
        total_arousal = 0.0
        count = 0

        for name in color_names:
            if name in self.COLOR_EMOTIONS:
                total_valence += self.COLOR_EMOTIONS[name]["valence"]
                total_arousal += self.COLOR_EMOTIONS[name]["arousal"]
                count += 1

        if count == 0:
            return {"valence": 0.5, "arousal": 0.5, "mood": "neutral"}

        valence = total_valence / count
        arousal = total_arousal / count

        # Map to mood quadrant
        if valence > 0.5 and arousal > 0.5:
            mood = "excited/energetic"
        elif valence > 0.5 and arousal <= 0.5:
            mood = "calm/content"
        elif valence <= 0.5 and arousal > 0.5:
            mood = "tense/urgent"
        else:
            mood = "somber/serious"

        return {
            "valence": round(valence, 2),
            "arousal": round(arousal, 2),
            "mood": mood,
            "amygdala_activation": round(
                arousal * 0.7 + abs(valence - 0.5) * 0.6, 2
            ),
        }

    def _hex_to_rgb(self, hex_color: str) -> tuple[int, int, int]:
        hex_color = hex_color.lstrip("#")
        if len(hex_color) == 3:
            hex_color = "".join(c * 2 for c in hex_color)
        if len(hex_color) != 6:
            return (128, 128, 128)  # default gray
        try:
            return (
                int(hex_color[0:2], 16),
                int(hex_color[2:4], 16),
                int(hex_color[4:6], 16),
            )
        except ValueError:
            return (128, 128, 128)

    def _rgb_to_hue(self, rgb: tuple[int, int, int]) -> float:
        r, g, b = [x / 255.0 for x in rgb]
        max_c = max(r, g, b)
        min_c = min(r, g, b)
        diff = max_c - min_c
        if diff == 0:
            return 0
        if max_c == r:
            hue = 60 * (((g - b) / diff) % 6)
        elif max_c == g:
            hue = 60 * (((b - r) / diff) + 2)
        else:
            hue = 60 * (((r - g) / diff) + 4)
        return hue % 360

    def _classify_color(self, rgb: tuple[int, int, int]) -> str:
        r, g, b = rgb
        # Grayscale check
        if max(r, g, b) - min(r, g, b) < 30:
            lum = 0.299 * r + 0.587 * g + 0.114 * b
            if lum < 50:
                return "black"
            if lum > 200:
                return "white"
            return "gray"

        hue = self._rgb_to_hue(rgb)
        if hue < 15 or hue >= 345:
            return "red"
        if hue < 45:
            return "orange"
        if hue < 70:
            return "yellow"
        if hue < 160:
            return "green"
        if hue < 250:
            return "blue"
        if hue < 330:
            return "purple"
        return "pink"

    def _is_complementary(self, hues: list[float]) -> bool:
        if len(hues) != 2:
            return False
        diff = abs(hues[0] - hues[1])
        return 150 < diff < 210

    def _is_analogous(self, hues: list[float]) -> bool:
        if len(hues) < 2:
            return False
        sorted_hues = sorted(hues)
        max_gap = max(
            sorted_hues[i + 1] - sorted_hues[i]
            for i in range(len(sorted_hues) - 1)
        )
        return max_gap < 60

    def _is_triadic(self, hues: list[float]) -> bool:
        if len(hues) != 3:
            return False
        sorted_hues = sorted(hues)
        gaps = [sorted_hues[i + 1] - sorted_hues[i] for i in range(2)]
        gaps.append(360 - sorted_hues[-1] + sorted_hues[0])
        return all(80 < g < 160 for g in gaps)
