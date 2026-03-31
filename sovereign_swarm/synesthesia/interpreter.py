"""Interprets cortical activations into actionable design recommendations.

Uses neuroscience-informed rules mapping brain region activations
to specific design recommendations. Falls back to Claude API for
nuanced interpretation when available.
"""

from __future__ import annotations

from typing import Any

from sovereign_swarm.synesthesia.models import (
    BrainRegion,
    CorticalActivation,
    DesignRecommendation,
    Modality,
    StimulusAnalysis,
)


class DesignInterpreter:
    """Interprets cortical activations into actionable design recommendations.

    Uses neuroscience-informed rules mapping brain region activations
    to specific design recommendations. Falls back to Claude API for
    nuanced interpretation when available.
    """

    def __init__(
        self, config: Any | None = None, ingest_bridge: Any | None = None
    ):
        self.config = config
        self.ingest = ingest_bridge
        self._client = None

    async def interpret(
        self, analysis: StimulusAnalysis
    ) -> list[DesignRecommendation]:
        """Generate design recommendations from brain activations."""
        recommendations: list[DesignRecommendation] = []

        for act in analysis.activations:
            recs = self._interpret_activation(act, analysis.modality)
            recommendations.extend(recs)

        # Cross-cutting recommendations
        if analysis.cognitive_load > 0.7:
            recommendations.append(
                DesignRecommendation(
                    category="cognitive_load",
                    recommendation="Reduce cognitive load — the design demands too much mental processing",
                    rationale=(
                        "High prefrontal cortex activation indicates excessive working memory demands. "
                        "Users will disengage or make errors."
                    ),
                    brain_regions=[BrainRegion.PFC, BrainRegion.ACC],
                    confidence=0.8,
                    priority="high",
                )
            )

        if analysis.emotional_valence < -0.3:
            recommendations.append(
                DesignRecommendation(
                    category="emotional",
                    recommendation="Address negative emotional response — the design may feel hostile or uncomfortable",
                    rationale=(
                        "Amygdala activation pattern suggests negative emotional processing. "
                        "Consider warmer colors, softer shapes, or more whitespace."
                    ),
                    brain_regions=[BrainRegion.AMG, BrainRegion.INS],
                    confidence=0.7,
                    priority="high",
                )
            )

        if analysis.attention_score < 0.3:
            recommendations.append(
                DesignRecommendation(
                    category="attention",
                    recommendation="Increase visual salience — key elements don't capture attention",
                    rationale="Low V1/V4 activation suggests insufficient contrast or visual hierarchy.",
                    brain_regions=[BrainRegion.V1, BrainRegion.V4],
                    confidence=0.6,
                    priority="medium",
                )
            )

        # Enrich with knowledge base if available
        if self.ingest and self.ingest.available:
            for rec in recommendations[:3]:  # Enrich top 3
                evidence = await self.ingest.search(
                    f"UI UX design {rec.category} neuroscience brain", limit=2
                )
                if evidence.get("results"):
                    rec.rationale += (
                        f"\n\nSupported by: "
                        f"{evidence['results'][0].get('document_title', '')}"
                    )

        return recommendations

    def _interpret_activation(
        self, act: CorticalActivation, modality: Modality
    ) -> list[DesignRecommendation]:
        """Interpret a single brain region activation."""
        recs: list[DesignRecommendation] = []

        if act.region == BrainRegion.V1 and act.activation < 0.3:
            recs.append(
                DesignRecommendation(
                    category="contrast",
                    recommendation="Increase contrast between foreground and background elements",
                    rationale=(
                        "Low primary visual cortex activation = insufficient edge detection = "
                        "poor figure-ground separation"
                    ),
                    brain_regions=[BrainRegion.V1],
                    confidence=0.7,
                    priority="high" if act.activation < 0.2 else "medium",
                )
            )

        if act.region == BrainRegion.V4 and act.activation < 0.3:
            recs.append(
                DesignRecommendation(
                    category="color",
                    recommendation="Enrich the color palette — current palette may feel bland or undifferentiated",
                    rationale="Low V4 activation indicates insufficient color stimulation for form/color processing",
                    brain_regions=[BrainRegion.V4],
                    confidence=0.6,
                    priority="medium",
                )
            )

        if act.region == BrainRegion.V4 and act.activation > 0.85:
            recs.append(
                DesignRecommendation(
                    category="color",
                    recommendation="Consider reducing color variety — palette may be overwhelming",
                    rationale="Very high V4 activation can indicate overstimulation from too many competing colors",
                    brain_regions=[BrainRegion.V4],
                    confidence=0.5,
                    priority="medium",
                )
            )

        if act.region == BrainRegion.VWFA and act.activation < 0.4:
            recs.append(
                DesignRecommendation(
                    category="typography",
                    recommendation=(
                        "Improve text readability — shorten sentences, use simpler words, "
                        "increase font size or line height"
                    ),
                    rationale=(
                        "Low visual word form area activation = reading requires conscious effort "
                        "instead of flowing naturally"
                    ),
                    brain_regions=[BrainRegion.VWFA],
                    confidence=0.7,
                    priority="high",
                )
            )

        if act.region == BrainRegion.ACC and act.activation > 0.7:
            recs.append(
                DesignRecommendation(
                    category="clarity",
                    recommendation="Resolve conflicting signals — users may feel uncertain about what to do next",
                    rationale=(
                        "High anterior cingulate activation = conflict detection = "
                        "mixed signals in the design"
                    ),
                    brain_regions=[BrainRegion.ACC],
                    confidence=0.6,
                    priority="high",
                )
            )

        if act.region == BrainRegion.PPA and modality == Modality.VISUAL:
            if act.activation < 0.4:
                recs.append(
                    DesignRecommendation(
                        category="layout",
                        recommendation=(
                            "Establish clearer spatial hierarchy — use grid alignment, "
                            "consistent spacing, and visual grouping"
                        ),
                        rationale="Low parahippocampal place area activation = brain struggling to parse spatial layout",
                        brain_regions=[BrainRegion.PPA],
                        confidence=0.6,
                        priority="medium",
                    )
                )

        return recs

    def compute_overall_score(self, analysis: StimulusAnalysis) -> float:
        """Compute 0-100 overall design score from brain activations."""
        if not analysis.activations:
            return 50.0

        # Scoring rubric (neuroscience-informed weights)
        scores = {
            "attention": min(analysis.attention_score * 25, 25),  # 0-25 points
            "cognitive_ease": max(0, (1 - analysis.cognitive_load)) * 25,  # 0-25
            "emotional": (analysis.emotional_valence + 1) / 2 * 25,  # 0-25 (maps -1..1 to 0..25)
            "aesthetic": analysis.aesthetic_score * 25,  # 0-25
        }

        return round(sum(scores.values()), 1)
