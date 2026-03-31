"""Maps perceptual features to predicted cortical activations.

Phase A: Neuroscience-informed heuristic mappings.
Phase B: TRIBE v2 Transformer for actual cortical surface predictions.
"""

from __future__ import annotations

from sovereign_swarm.synesthesia.models import BrainRegion, CorticalActivation


class BrainMapper:
    """Maps perceptual features to predicted cortical activations.

    Phase A: Neuroscience-informed heuristic mappings based on established
    brain-stimulus-response literature.
    Phase B: TRIBE v2 Transformer for actual cortical surface predictions.
    """

    def __init__(self, use_tribe: bool = False):
        self.use_tribe = use_tribe

    def map_visual(self, features: dict) -> list[CorticalActivation]:
        """Map visual features to brain region activations."""
        activations = []

        # V1 (Primary Visual): responds to contrast, edges
        contrast = features.get("estimated_contrast", 0.5)
        activations.append(
            CorticalActivation(
                region=BrainRegion.V1,
                activation=contrast,
                interpretation=(
                    f"Edge/contrast detection: "
                    f"{'high' if contrast > 0.7 else 'moderate' if contrast > 0.4 else 'low'} "
                    f"visual salience"
                ),
            )
        )

        # V4 (Color/Form): responds to color richness and harmony
        color_harmony = features.get("color_harmony", 0.5)
        color_count = features.get("color_count", 0)
        v4_activation = min(1.0, (color_count / 5) * 0.5 + color_harmony * 0.5)
        activations.append(
            CorticalActivation(
                region=BrainRegion.V4,
                activation=v4_activation,
                interpretation=(
                    f"Color processing: {color_count} colors with "
                    f"{'high' if color_harmony > 0.7 else 'moderate' if color_harmony > 0.4 else 'low'} "
                    f"harmony"
                ),
            )
        )

        # PFC (Prefrontal): cognitive load from visual complexity
        complexity = features.get("estimated_complexity", 0.5)
        activations.append(
            CorticalActivation(
                region=BrainRegion.PFC,
                activation=complexity,
                interpretation=(
                    f"Cognitive load: "
                    f"{'high' if complexity > 0.7 else 'moderate' if complexity > 0.4 else 'low'}"
                    f" — {'consider simplifying' if complexity > 0.7 else 'good balance'}"
                ),
            )
        )

        # AMG (Amygdala): emotional response
        has_warm = features.get("has_warm_colors", False)
        emotional = 0.6 if has_warm else 0.3
        activations.append(
            CorticalActivation(
                region=BrainRegion.AMG,
                activation=emotional,
                interpretation=(
                    f"Emotional activation: "
                    f"{'warm tones drive engagement' if has_warm else 'cool tones promote calm/trust'}"
                ),
            )
        )

        # INS (Insula): aesthetic/visceral response
        aesthetic = color_harmony * 0.6 + (1 - complexity) * 0.4
        activations.append(
            CorticalActivation(
                region=BrainRegion.INS,
                activation=aesthetic,
                interpretation=(
                    f"Aesthetic response: "
                    f"{'pleasing' if aesthetic > 0.6 else 'neutral' if aesthetic > 0.3 else 'potentially uncomfortable'}"
                ),
            )
        )

        # PPA (Parahippocampal Place Area): layout/spatial processing
        activations.append(
            CorticalActivation(
                region=BrainRegion.PPA,
                activation=0.5 + (1 - complexity) * 0.3,
                interpretation="Layout recognition: clear spatial hierarchy aids navigation",
            )
        )

        return activations

    def map_audio(self, features: dict) -> list[CorticalActivation]:
        """Map audio features to brain region activations."""
        activations = []

        volume = features.get("estimated_volume", 0.5)
        pleasantness = features.get("estimated_pleasantness", 0.5)
        tempo = features.get("estimated_tempo", "moderate")

        activations.append(
            CorticalActivation(
                region=BrainRegion.A1,
                activation=volume,
                interpretation=(
                    f"Auditory processing: "
                    f"{'high' if volume > 0.7 else 'moderate' if volume > 0.3 else 'subtle'} "
                    f"sound presence"
                ),
            )
        )

        activations.append(
            CorticalActivation(
                region=BrainRegion.STG,
                activation=0.5 if tempo == "moderate" else 0.7,
                interpretation=(
                    f"Temporal processing: {tempo} tempo "
                    f"{'maintains attention' if tempo == 'moderate' else 'drives energy' if tempo == 'fast' else 'promotes relaxation'}"
                ),
            )
        )

        activations.append(
            CorticalActivation(
                region=BrainRegion.AMG,
                activation=(
                    1.0 - pleasantness
                    if pleasantness < 0.5
                    else pleasantness * 0.5
                ),
                interpretation=(
                    f"Emotional response to audio: "
                    f"{'pleasant/soothing' if pleasantness > 0.6 else 'neutral' if pleasantness > 0.4 else 'potentially jarring — consider softer alternatives'}"
                ),
            )
        )

        activations.append(
            CorticalActivation(
                region=BrainRegion.PFC,
                activation=volume * 0.7 + (0.3 if tempo == "fast" else 0.1),
                interpretation=(
                    f"Audio cognitive load: "
                    f"{'high — may distract from primary task' if volume > 0.7 else 'manageable background presence'}"
                ),
            )
        )

        return activations

    def map_text(self, features: dict) -> list[CorticalActivation]:
        """Map text features to brain region activations."""
        activations = []

        readability = features.get("readability", 0.5)
        cognitive_load = features.get("cognitive_load", 0.5)
        tech_density = features.get("technical_density", 0)

        activations.append(
            CorticalActivation(
                region=BrainRegion.VWFA,
                activation=min(1.0, readability * 0.7 + 0.3),
                interpretation=(
                    f"Reading fluency: "
                    f"{'effortless' if readability > 0.7 else 'moderate effort' if readability > 0.4 else 'difficult — simplify vocabulary and sentence length'}"
                ),
            )
        )

        activations.append(
            CorticalActivation(
                region=BrainRegion.PFC,
                activation=cognitive_load,
                interpretation=(
                    f"Text cognitive load: "
                    f"{'high — readers may disengage' if cognitive_load > 0.7 else 'moderate' if cognitive_load > 0.4 else 'low — easy to process'}"
                ),
            )
        )

        activations.append(
            CorticalActivation(
                region=BrainRegion.STG,
                activation=readability * 0.8,
                interpretation=(
                    f"Language comprehension: "
                    f"{'flowing naturally' if readability > 0.6 else 'requires deliberate processing'}"
                ),
            )
        )

        activations.append(
            CorticalActivation(
                region=BrainRegion.ACC,
                activation=tech_density * 0.8 + cognitive_load * 0.2,
                interpretation=(
                    f"Conflict monitoring: "
                    f"{'technical jargon may confuse general audience' if tech_density > 0.2 else 'accessible language'}"
                ),
            )
        )

        return activations

    def compute_cross_modal_harmony(
        self, all_activations: list[list[CorticalActivation]]
    ) -> float:
        """Compute harmony score across modalities.

        High harmony = brain regions activated consistently across modalities.
        Low harmony = conflicting signals (e.g., calming visuals + jarring audio).
        """
        if len(all_activations) < 2:
            return 1.0

        # For each shared region, check if activation levels are compatible
        region_activations: dict[BrainRegion, list[float]] = {}
        for activation_set in all_activations:
            for act in activation_set:
                region_activations.setdefault(act.region, []).append(act.activation)

        # Harmony = 1 - average variance across shared regions
        variances = []
        for region, acts in region_activations.items():
            if len(acts) > 1:
                mean = sum(acts) / len(acts)
                variance = sum((a - mean) ** 2 for a in acts) / len(acts)
                variances.append(variance)

        if not variances:
            return 1.0

        avg_variance = sum(variances) / len(variances)
        return max(0.0, 1.0 - avg_variance * 4)  # Scale: variance of 0.25 = harmony of 0
