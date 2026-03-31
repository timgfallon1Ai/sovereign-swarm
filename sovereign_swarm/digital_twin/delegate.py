"""Delegate interface -- allows authorized humans to query Tim's AI."""

from __future__ import annotations

from typing import Any

import structlog

from sovereign_swarm.digital_twin.models import DelegateQuery, DelegateResponse

logger = structlog.get_logger()

# Access level permissions
_ACCESS_PERMISSIONS: dict[str, dict[str, bool]] = {
    "viewer": {
        "factual_qa": True,
        "action_recommendations": False,
        "full_reasoning": False,
        "financial_info": False,
    },
    "operator": {
        "factual_qa": True,
        "action_recommendations": True,
        "full_reasoning": False,
        "financial_info": False,
    },
    "admin": {
        "factual_qa": True,
        "action_recommendations": True,
        "full_reasoning": True,
        "financial_info": True,
    },
}

# Confidence threshold below which queries are escalated to Tim
_ESCALATION_THRESHOLD = 0.5

# Domains that always escalate regardless of confidence
_ALWAYS_ESCALATE_DOMAINS = {"financial", "legal", "contracts", "hiring"}


class DelegateInterface:
    """Allows authorized humans to query Tim's AI when Tim is unavailable."""

    def __init__(self, cognitive_model: Any | None = None) -> None:
        self._cognitive_model = cognitive_model
        self._query_log: list[dict[str, Any]] = []
        self._escalation_queue: list[dict[str, Any]] = []

    def handle_query(self, query: DelegateQuery) -> DelegateResponse:
        """Process a delegate query based on access level."""
        permissions = _ACCESS_PERMISSIONS.get(query.access_level, _ACCESS_PERMISSIONS["viewer"])

        # Log the query
        self._query_log.append(
            {
                "query": query.query,
                "requester": query.requester,
                "access_level": query.access_level,
            }
        )

        # Detect domain and check if escalation is needed
        domain = self._detect_domain(query.query)
        needs_escalation = domain in _ALWAYS_ESCALATE_DOMAINS

        # Generate response using cognitive model
        if self._cognitive_model:
            response_text = self._cognitive_model.generate_response(
                query.query, context=query.context
            )
            confidence = 0.7
        else:
            response_text = self._generate_basic_response(query, permissions)
            confidence = 0.4

        # Check confidence threshold
        if confidence < _ESCALATION_THRESHOLD or needs_escalation:
            self._escalation_queue.append(
                {
                    "query": query.model_dump(),
                    "reason": f"{'Domain requires escalation' if needs_escalation else 'Low confidence'} ({domain})",
                    "preliminary_response": response_text,
                }
            )

            if needs_escalation and not permissions.get("financial_info"):
                response_text = (
                    f"This query touches {domain} matters and has been queued for Tim's review. "
                    "I'll provide a response once Tim reviews and approves."
                )
                confidence = 0.3

        # Filter response based on access level
        if not permissions.get("action_recommendations") and "recommend" in response_text.lower():
            response_text = self._strip_recommendations(response_text)

        return DelegateResponse(
            response=response_text,
            confidence=round(confidence, 2),
            sources=["cognitive_model", "decision_patterns"],
            disclaimer="This is an AI-generated response based on Tim's patterns and knowledge.",
        )

    @staticmethod
    def _generate_basic_response(
        query: DelegateQuery, permissions: dict[str, bool]
    ) -> str:
        """Generate a basic response without the cognitive model."""
        if not permissions.get("factual_qa"):
            return "Access level does not permit responses to this query."

        return (
            f"Regarding your question about '{query.query[:100]}': "
            "I don't have enough context from Tim's cognitive model to provide "
            "a confident answer. This has been queued for Tim's direct review."
        )

    @staticmethod
    def _strip_recommendations(text: str) -> str:
        """Remove action recommendations from a response (for viewer access)."""
        sentences = text.split(". ")
        filtered = [
            s
            for s in sentences
            if not any(
                word in s.lower()
                for word in ["recommend", "should", "suggest", "advise"]
            )
        ]
        return ". ".join(filtered) if filtered else text

    @staticmethod
    def _detect_domain(text: str) -> str:
        """Detect the domain of a query."""
        text_lower = text.lower()
        domain_map: dict[str, list[str]] = {
            "financial": ["money", "payment", "invoice", "budget", "cost", "revenue", "p&l"],
            "legal": ["contract", "legal", "compliance", "regulation", "liability"],
            "hiring": ["hire", "candidate", "interview", "staff", "employee"],
            "engineering": ["code", "deploy", "bug", "api", "database", "server"],
            "operations": ["schedule", "meeting", "project", "deadline", "task"],
        }

        for domain, keywords in domain_map.items():
            if any(kw in text_lower for kw in keywords):
                return domain
        return "general"

    def get_escalation_queue(self) -> list[dict[str, Any]]:
        """Return queries queued for Tim's review."""
        return self._escalation_queue

    def clear_escalation(self, index: int | None = None) -> int:
        """Clear escalation queue (all or by index). Returns count cleared."""
        if index is not None:
            if 0 <= index < len(self._escalation_queue):
                self._escalation_queue.pop(index)
                return 1
            return 0
        count = len(self._escalation_queue)
        self._escalation_queue.clear()
        return count

    def get_query_log(self) -> list[dict[str, Any]]:
        """Return the query log."""
        return self._query_log
