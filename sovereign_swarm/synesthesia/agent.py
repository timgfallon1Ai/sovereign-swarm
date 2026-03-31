"""SynesthesiaAgent -- brain-informed UI/UX design analysis for the swarm."""

from __future__ import annotations

from typing import Any

import structlog

from sovereign_swarm.protocol.swarm_agent import (
    SwarmAgent,
    SwarmAgentCard,
    SwarmAgentRequest,
    SwarmAgentResponse,
)
from sovereign_swarm.synesthesia.models import (
    BrainRegion,
    ColorProfile,
    DesignRecommendation,
    DesignReview,
    Modality,
    StimulusAnalysis,
)

logger = structlog.get_logger()


class SynesthesiaAgent(SwarmAgent):
    """Synthetic synesthesia agent for brain-informed UI/UX design analysis.

    Combines TRIBE v2-inspired multimodal perception with neuroscience-informed
    brain mapping to generate design recommendations grounded in how the human
    brain actually processes visual, auditory, and textual stimuli.
    """

    def __init__(
        self,
        ingest_bridge: Any | None = None,
        config: Any | None = None,
    ):
        self.ingest = ingest_bridge
        self.config = config
        self._perception: Any | None = None
        self._mapper: Any | None = None
        self._interpreter: Any | None = None
        self._color_engine: Any | None = None

    @property
    def card(self) -> SwarmAgentCard:
        return SwarmAgentCard(
            name="synesthesia",
            description=(
                "Brain-informed UI/UX design analysis — predicts cortical responses "
                "to visual, audio, and text stimuli using TRIBE v2-inspired synthetic synesthesia"
            ),
            domains=[
                "design",
                "ui",
                "ux",
                "color",
                "typography",
                "layout",
                "audio",
                "accessibility",
            ],
            supported_intents=[
                "design_review",
                "color_analysis",
                "typography_review",
                "layout_analysis",
                "accessibility_check",
                "ab_test",
                "design",
            ],
            capabilities=[
                "design_review",
                "color_analysis",
                "text_readability",
                "audio_ux",
                "cross_modal_harmony",
                "ab_comparison",
                "emotional_response",
            ],
        )

    async def execute(self, request: SwarmAgentRequest) -> SwarmAgentResponse:
        """Execute a design analysis task."""
        task = request.task.lower()
        params = request.parameters or request.context or {}

        try:
            # Route to appropriate analysis
            if "color" in task or "palette" in task:
                result = await self._analyze_colors(params)
            elif "text" in task or "readability" in task or "copy" in task:
                result = await self._analyze_text(params)
            elif "audio" in task or "sound" in task:
                result = await self._analyze_audio(params)
            elif "compare" in task or "a/b" in task or "versus" in task:
                result = await self._ab_compare(params)
            else:
                result = await self._full_design_review(request.task, params)

            return SwarmAgentResponse(
                agent_name="synesthesia",
                status="success",
                output=result.get("markdown", str(result)),
                data=result,
                confidence=result.get("confidence", 0.7),
            )
        except Exception as e:
            logger.error("synesthesia.execute_failed", error=str(e))
            return SwarmAgentResponse(
                agent_name="synesthesia",
                status="error",
                error=str(e),
            )

    async def _full_design_review(
        self, description: str, params: dict
    ) -> dict:
        """Full multimodal design review."""
        perception = self._get_perception()
        mapper = self._get_mapper()
        interpreter = self._get_interpreter()
        color_engine = self._get_color_engine()

        all_activations: list[list] = []
        analyses: list[StimulusAnalysis] = []

        # Visual analysis
        colors = params.get("colors", [])
        visual_features = await perception.analyze_visual(
            description=description, colors=colors
        )
        visual_acts = mapper.map_visual(visual_features)
        all_activations.append(visual_acts)

        visual_analysis = StimulusAnalysis(
            modality=Modality.VISUAL,
            stimulus_description=description,
            activations=visual_acts,
            attention_score=visual_features.get("estimated_contrast", 0.5),
            cognitive_load=visual_features.get("estimated_complexity", 0.5),
            aesthetic_score=visual_features.get("color_harmony", 0.5),
        )
        analyses.append(visual_analysis)

        # Text analysis if text provided
        text = params.get("text", params.get("copy", ""))
        if text:
            text_features = await perception.analyze_text(text)
            text_acts = mapper.map_text(text_features)
            all_activations.append(text_acts)

            text_analysis = StimulusAnalysis(
                modality=Modality.TEXT,
                stimulus_description=f"Copy: {text[:100]}...",
                activations=text_acts,
                cognitive_load=text_features.get("cognitive_load", 0.5),
            )
            analyses.append(text_analysis)

        # Audio analysis if described
        audio_desc = params.get("audio", params.get("sound", ""))
        if audio_desc:
            audio_features = await perception.analyze_audio(description=audio_desc)
            audio_acts = mapper.map_audio(audio_features)
            all_activations.append(audio_acts)

            audio_analysis = StimulusAnalysis(
                modality=Modality.AUDIO,
                stimulus_description=audio_desc,
                activations=audio_acts,
            )
            analyses.append(audio_analysis)

        # Cross-modal harmony
        harmony = mapper.compute_cross_modal_harmony(all_activations)

        # Color-specific analysis
        color_profile: ColorProfile | None = None
        if colors:
            color_profile = color_engine.analyze_palette(colors)
            emotional = color_engine.predict_emotional_response(colors)
            for a in analyses:
                if a.modality == Modality.VISUAL:
                    a.emotional_valence = emotional["valence"] * 2 - 1  # 0..1 -> -1..1
                    a.emotional_arousal = emotional["arousal"]
                    a.harmony_score = harmony

        # Generate recommendations
        all_recs: list[DesignRecommendation] = []
        for analysis in analyses:
            analysis.harmony_score = harmony
            recs = await interpreter.interpret(analysis)
            all_recs.extend(recs)
            analysis.attention_score = self._compute_attention(analysis)

        # Compute overall score
        primary = analyses[0] if analyses else None
        overall_score = interpreter.compute_overall_score(primary) if primary else 50

        # Build review
        review = DesignReview(
            title=f"Design Review: {description[:60]}",
            analyses=analyses,
            recommendations=sorted(
                all_recs,
                key=lambda r: {"high": 0, "medium": 1, "low": 2}.get(r.priority, 1),
            ),
            overall_score=overall_score,
            summary=self._build_summary(analyses, all_recs, overall_score, harmony),
        )

        # Build markdown output
        markdown = self._review_to_markdown(review, color_profile)

        return {
            "review": review.model_dump(),
            "markdown": markdown,
            "overall_score": overall_score,
            "harmony_score": harmony,
            "confidence": 0.7,
        }

    async def _analyze_colors(self, params: dict) -> dict:
        colors = params.get("colors", params.get("palette", []))
        if not colors:
            return {
                "error": "No colors provided. Pass 'colors': ['#hex1', '#hex2', ...]"
            }

        engine = self._get_color_engine()
        profile = engine.analyze_palette(colors)
        harmony = engine.score_palette_harmony(colors)
        emotional = engine.predict_emotional_response(colors)

        markdown = f"""## Color Palette Analysis

**Colors**: {', '.join(colors)}
**Harmony Type**: {harmony['harmony_type']} (score: {harmony['score']:.0%})
**Warm/Cool Ratio**: {profile.warm_cool_ratio:.0%} warm
**Contrast**: {profile.contrast_ratio:.0%}
**V4 Cortical Activation**: {profile.v4_activation:.0%}

### Emotional Response
- **Mood**: {emotional['mood']}
- **Valence**: {emotional['valence']:.0%} (0=negative, 1=positive)
- **Arousal**: {emotional['arousal']:.0%} (0=calm, 1=exciting)
- **Amygdala Activation**: {emotional['amygdala_activation']:.0%}

### Associations
{', '.join(profile.emotional_associations)}

### Brain Note
{harmony.get('brain_note', '')}
"""
        return {
            "markdown": markdown,
            "profile": profile.model_dump(),
            "harmony": harmony,
            "emotional": emotional,
            "confidence": 0.75,
        }

    async def _analyze_text(self, params: dict) -> dict:
        text = params.get("text", params.get("copy", ""))
        if not text:
            return {"error": "No text provided. Pass 'text': 'your copy here'"}

        perception = self._get_perception()
        mapper = self._get_mapper()

        features = await perception.analyze_text(text)
        activations = mapper.map_text(features)

        markdown = f"""## Text/Copy Readability Analysis

**Word Count**: {features['word_count']}
**Avg Word Length**: {features['avg_word_length']} chars
**Avg Sentence Length**: {features['avg_sentence_length']} words
**Readability**: {features['readability']:.0%}
**Cognitive Load**: {features['cognitive_load']:.0%}
**Technical Density**: {features['technical_density']:.0%}

### Brain Response
"""
        for act in activations:
            markdown += f"- **{act.region.value}** ({act.activation:.0%}): {act.interpretation}\n"

        return {"markdown": markdown, "features": features, "confidence": 0.7}

    async def _analyze_audio(self, params: dict) -> dict:
        desc = params.get(
            "audio", params.get("sound", params.get("description", ""))
        )
        if not desc:
            return {"error": "No audio description provided."}

        perception = self._get_perception()
        mapper = self._get_mapper()
        features = await perception.analyze_audio(description=desc)
        activations = mapper.map_audio(features)

        markdown = f"## Audio UX Analysis\n\n**Description**: {desc}\n\n### Brain Response\n"
        for act in activations:
            markdown += f"- **{act.region.value}** ({act.activation:.0%}): {act.interpretation}\n"

        return {"markdown": markdown, "features": features, "confidence": 0.6}

    async def _ab_compare(self, params: dict) -> dict:
        """Compare two design variants."""
        variant_a = params.get("a", params.get("variant_a", {}))
        variant_b = params.get("b", params.get("variant_b", {}))

        result_a = await self._full_design_review(
            variant_a.get("description", "Variant A"), variant_a
        )
        result_b = await self._full_design_review(
            variant_b.get("description", "Variant B"), variant_b
        )

        score_a = result_a.get("overall_score", 50)
        score_b = result_b.get("overall_score", 50)
        winner = "A" if score_a > score_b else "B" if score_b > score_a else "Tie"

        markdown = f"""## A/B Design Comparison

| Metric | Variant A | Variant B |
|--------|-----------|-----------|
| **Overall Score** | {score_a:.0f}/100 | {score_b:.0f}/100 |
| **Harmony** | {result_a.get('harmony_score', 0):.0%} | {result_b.get('harmony_score', 0):.0%} |

**Predicted Winner**: Variant {winner}
"""
        return {
            "markdown": markdown,
            "winner": winner,
            "score_a": score_a,
            "score_b": score_b,
            "confidence": 0.65,
        }

    def _compute_attention(self, analysis: StimulusAnalysis) -> float:
        v1 = next(
            (a.activation for a in analysis.activations if a.region == BrainRegion.V1),
            0.5,
        )
        v4 = next(
            (a.activation for a in analysis.activations if a.region == BrainRegion.V4),
            0.5,
        )
        return v1 * 0.6 + v4 * 0.4

    def _build_summary(
        self,
        analyses: list[StimulusAnalysis],
        recs: list[DesignRecommendation],
        score: float,
        harmony: float,
    ) -> str:
        high_priority = [r for r in recs if r.priority == "high"]
        parts = [f"Overall design score: {score:.0f}/100."]
        if harmony < 0.5:
            parts.append(
                f"Cross-modal harmony is low ({harmony:.0%}) — "
                f"visual, text, and audio elements may conflict."
            )
        if high_priority:
            parts.append(f"{len(high_priority)} high-priority issue(s) found.")
        return " ".join(parts)

    def _review_to_markdown(
        self, review: DesignReview, color_profile: ColorProfile | None = None
    ) -> str:
        sections = [
            f"# {review.title}",
            f"\n**Score: {review.overall_score:.0f}/100**\n",
            review.summary,
        ]

        for analysis in review.analyses:
            sections.append(f"\n## {analysis.modality.value.title()} Analysis")
            sections.append(f"- Attention: {analysis.attention_score:.0%}")
            sections.append(f"- Cognitive Load: {analysis.cognitive_load:.0%}")
            sections.append(f"- Harmony: {analysis.harmony_score:.0%}")
            sections.append("\n### Brain Activations")
            for act in analysis.activations:
                sections.append(
                    f"- **{act.region.value}** ({act.activation:.0%}): {act.interpretation}"
                )

        if review.recommendations:
            sections.append("\n## Recommendations")
            for i, rec in enumerate(review.recommendations, 1):
                sections.append(
                    f"\n### {i}. [{rec.priority.upper()}] {rec.category.title()}"
                )
                sections.append(rec.recommendation)
                sections.append(f"*Rationale: {rec.rationale}*")

        return "\n".join(sections)

    # Lazy initializers
    def _get_perception(self) -> Any:
        if not self._perception:
            from sovereign_swarm.synesthesia.perception import PerceptionEngine

            self._perception = PerceptionEngine()
        return self._perception

    def _get_mapper(self) -> Any:
        if not self._mapper:
            from sovereign_swarm.synesthesia.brain_mapper import BrainMapper

            self._mapper = BrainMapper()
        return self._mapper

    def _get_interpreter(self) -> Any:
        if not self._interpreter:
            from sovereign_swarm.synesthesia.interpreter import DesignInterpreter

            self._interpreter = DesignInterpreter(
                config=self.config, ingest_bridge=self.ingest
            )
        return self._interpreter

    def _get_color_engine(self) -> Any:
        if not self._color_engine:
            from sovereign_swarm.synesthesia.color_engine import ColorEngine

            self._color_engine = ColorEngine()
        return self._color_engine
