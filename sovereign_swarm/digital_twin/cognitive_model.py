"""Cognitive model -- models Tim's decision-making patterns."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import structlog

from sovereign_swarm.digital_twin.models import (
    CognitiveSnapshot,
    DecisionPattern,
)

logger = structlog.get_logger()

# Initial cognitive profile seeded from known patterns
_INITIAL_PATTERNS: list[DecisionPattern] = [
    DecisionPattern(
        domain="trading",
        pattern_description="Prefers asymmetric risk/reward setups (min 2:1 R/R). Sizes positions based on conviction level. Quick to cut losers.",
        frequency=50,
        confidence=0.85,
        examples=[
            "Takes Kalshi positions on high-conviction events with defined max loss",
            "Uses gap arbitrage between prediction market platforms",
        ],
    ),
    DecisionPattern(
        domain="engineering",
        pattern_description="Favors pragmatic over perfect. Ships iterative MVPs. Python-first with strong typing. Prefers composition over inheritance.",
        frequency=100,
        confidence=0.9,
        examples=[
            "Builds Phase A stubs first, wires real implementations in Phase B",
            "Uses pydantic models for data validation throughout",
        ],
    ),
    DecisionPattern(
        domain="hiring",
        pattern_description="Values self-starters and async communicators. Prefers contractors for GBB. Tests with small paid projects before committing.",
        frequency=20,
        confidence=0.7,
        examples=[
            "Starts with a trial project to assess fit",
            "Prioritizes candidates who show initiative",
        ],
    ),
    DecisionPattern(
        domain="design",
        pattern_description="Clean, minimal aesthetics. Dark mode preferred. Data-dense dashboards. Inspired by Dieter Rams principles.",
        frequency=30,
        confidence=0.8,
        examples=[
            "Prefers Inter/JetBrains Mono fonts",
            "Likes dark sidebars with high-contrast data cards",
        ],
    ),
    DecisionPattern(
        domain="communication",
        pattern_description="Direct and concise. Prefers async (Slack/email) over meetings. Uses structured formats for complex topics.",
        frequency=100,
        confidence=0.9,
        examples=[
            "Sends bullet-point updates rather than long paragraphs",
            "Schedules meetings only when async won't resolve the issue",
        ],
    ),
]

_INITIAL_RISK_TOLERANCE: dict[str, float] = {
    "trading": 0.6,          # moderate -- defined risk per trade
    "engineering": 0.8,       # high -- willing to try new tools/approaches
    "hiring": 0.4,            # conservative -- careful with commitments
    "financial_commitment": 0.3,  # low -- careful with large expenses
    "public_content": 0.5,    # moderate -- balances visibility with reputation
}

_INITIAL_EXPERTISE: list[str] = [
    "AI/ML engineering",
    "Full-stack development (Python, TypeScript, React)",
    "Trading systems (prediction markets, equities)",
    "Data engineering (ingestion pipelines, knowledge graphs)",
    "System architecture (multi-agent, microservices)",
    "Business operations (GBB, Sovereign Mind)",
    "UI/UX design",
]


class CognitiveModel:
    """Models Tim's decision-making patterns for delegation and continuity."""

    def __init__(self) -> None:
        self._patterns: list[DecisionPattern] = list(_INITIAL_PATTERNS)
        self._risk_tolerance: dict[str, float] = dict(_INITIAL_RISK_TOLERANCE)
        self._expertise: list[str] = list(_INITIAL_EXPERTISE)
        self._communication_style: dict[str, Any] = {
            "tone": "direct",
            "format": "structured",
            "preferred_channels": ["slack", "email"],
            "meeting_preference": "async_first",
        }
        self._active_projects: list[str] = [
            "sovereign-swarm",
            "sovereign-ai",
            "sovereign-ingest",
            "journalclub-kb",
            "GBB operations",
            "ATS trading system",
        ]

    def get_snapshot(self) -> CognitiveSnapshot:
        """Return a point-in-time snapshot of the cognitive model."""
        return CognitiveSnapshot(
            active_projects=self._active_projects,
            decision_patterns=self._patterns,
            communication_style=self._communication_style,
            risk_tolerance=self._risk_tolerance,
            expertise_areas=self._expertise,
        )

    def predict_decision(
        self, scenario: str, options: list[str], domain: str = ""
    ) -> dict[str, Any]:
        """Predict which option Tim would choose based on historical patterns.

        Returns the predicted choice, confidence, and reasoning.
        """
        # Find relevant patterns
        relevant = [p for p in self._patterns if p.domain == domain] if domain else self._patterns

        if not relevant:
            return {
                "prediction": options[0] if options else "",
                "confidence": 0.2,
                "reasoning": "No historical patterns for this domain. Low confidence prediction.",
                "domain": domain or "unknown",
            }

        # Use pattern matching to score options
        best_option = options[0] if options else ""
        best_score = 0.0
        reasoning_parts: list[str] = []

        for pattern in relevant:
            pattern_text = pattern.pattern_description.lower()
            for option in options:
                option_lower = option.lower()
                # Simple keyword overlap scoring
                words = set(pattern_text.split())
                option_words = set(option_lower.split())
                overlap = len(words & option_words)
                score = overlap * pattern.confidence

                if score > best_score:
                    best_score = score
                    best_option = option
                    reasoning_parts.append(
                        f"Matches pattern: {pattern.pattern_description[:80]}..."
                    )

        avg_confidence = (
            sum(p.confidence for p in relevant) / len(relevant)
            if relevant
            else 0.3
        )

        return {
            "prediction": best_option,
            "confidence": round(min(avg_confidence, 0.9), 2),
            "reasoning": " | ".join(reasoning_parts[:3]) if reasoning_parts else "Based on general domain patterns",
            "domain": domain or "general",
            "patterns_consulted": len(relevant),
        }

    def generate_response(self, query: str, context: dict[str, Any] | None = None) -> str:
        """Generate a response the way Tim would, using learned patterns.

        Phase A: template-based with pattern insertion.
        Phase B: Claude-powered with full cognitive context.
        """
        context = context or {}
        domain = self._detect_domain(query)
        patterns = [p for p in self._patterns if p.domain == domain]

        # Build a Tim-style response
        parts: list[str] = []

        if patterns:
            primary_pattern = patterns[0]
            parts.append(f"Based on my approach to {domain}:")
            parts.append(primary_pattern.pattern_description)

        # Add risk tolerance context
        risk = self._risk_tolerance.get(domain, 0.5)
        if risk < 0.4:
            parts.append("I'd be conservative here -- let's validate before committing.")
        elif risk > 0.7:
            parts.append("I'm comfortable moving forward quickly on this.")

        if not parts:
            parts.append(
                "I'd need to think about this more carefully. "
                "Can you provide more context?"
            )

        return " ".join(parts)

    def update_pattern(self, domain: str, description: str, example: str = "") -> None:
        """Update or add a decision pattern."""
        for pattern in self._patterns:
            if pattern.domain == domain:
                pattern.pattern_description = description
                pattern.frequency += 1
                if example:
                    pattern.examples.append(example)
                logger.info("cognitive_model.pattern_updated", domain=domain)
                return

        # New pattern
        new_pattern = DecisionPattern(
            domain=domain,
            pattern_description=description,
            frequency=1,
            confidence=0.5,
            examples=[example] if example else [],
        )
        self._patterns.append(new_pattern)
        logger.info("cognitive_model.pattern_added", domain=domain)

    def _detect_domain(self, text: str) -> str:
        """Simple domain detection from text keywords."""
        text_lower = text.lower()
        domain_keywords: dict[str, list[str]] = {
            "trading": ["trade", "position", "market", "kalshi", "stock", "p&l"],
            "engineering": ["code", "build", "deploy", "api", "database", "python"],
            "hiring": ["hire", "candidate", "interview", "contractor", "staff"],
            "design": ["design", "ui", "ux", "dashboard", "layout", "color"],
            "communication": ["email", "slack", "meeting", "message", "respond"],
        }

        best_domain = "general"
        best_count = 0
        for domain, keywords in domain_keywords.items():
            count = sum(1 for kw in keywords if kw in text_lower)
            if count > best_count:
                best_count = count
                best_domain = domain

        return best_domain
