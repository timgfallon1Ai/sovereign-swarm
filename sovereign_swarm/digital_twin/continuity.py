"""Continuity management -- operates the system within defined bounds when Tim is unavailable."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import structlog

from sovereign_swarm.digital_twin.models import ContinuityProtocol

logger = structlog.get_logger()

# Patterns that trigger auto-responses
_AUTO_RESPONSE_PATTERNS: dict[str, str] = {
    "hours": "Tim's typical working hours are 9 AM - 7 PM CT, Monday through Friday. He may respond outside these hours for urgent matters.",
    "schedule": "Tim is currently unavailable. For scheduling, please suggest a few times and he will confirm when he returns.",
    "availability": "Tim is currently away. The system is operating in continuity mode. Routine queries are being handled automatically; complex decisions are queued for his return.",
    "contact": "For urgent matters, please reach out to the designated escalation contacts. For non-urgent items, your request has been logged and Tim will review it upon his return.",
    "pricing": "For pricing information, please refer to the service agreement or wait for Tim's return to discuss custom arrangements.",
}


class ContinuityManager:
    """Manages the continuity protocol when Tim is unavailable."""

    def __init__(self) -> None:
        self._protocol = ContinuityProtocol()

    def activate(
        self,
        escalation_contacts: list[dict[str, str]] | None = None,
        auto_responses: bool = True,
    ) -> ContinuityProtocol:
        """Activate continuity mode."""
        self._protocol.active = True
        self._protocol.activated_at = datetime.utcnow()
        self._protocol.auto_responses_enabled = auto_responses

        if escalation_contacts:
            self._protocol.escalation_contacts = escalation_contacts

        logger.info(
            "continuity.activated",
            auto_responses=auto_responses,
            escalation_contacts=len(self._protocol.escalation_contacts),
        )
        return self._protocol

    def deactivate(self) -> ContinuityProtocol:
        """Deactivate continuity mode."""
        self._protocol.active = False
        queued = len(self._protocol.queued_decisions)
        logger.info("continuity.deactivated", queued_decisions=queued)
        return self._protocol

    def get_status(self) -> dict[str, Any]:
        """Return the current continuity status."""
        return {
            "active": self._protocol.active,
            "activated_at": str(self._protocol.activated_at) if self._protocol.activated_at else None,
            "auto_responses_enabled": self._protocol.auto_responses_enabled,
            "queued_decisions": len(self._protocol.queued_decisions),
            "boundaries": self._protocol.boundaries,
            "escalation_contacts": self._protocol.escalation_contacts,
            "max_autonomy_level": self._protocol.max_autonomy_level,
        }

    def handle_incoming(self, query: str, requester: str = "") -> dict[str, Any]:
        """Handle an incoming query during continuity mode.

        Returns: auto-response if matched, or queues for Tim's return.
        """
        if not self._protocol.active:
            return {
                "action": "passthrough",
                "message": "Continuity mode not active. Routing normally.",
            }

        # Check if this is a routine query we can auto-respond to
        if self._protocol.auto_responses_enabled:
            auto_response = self._match_auto_response(query)
            if auto_response:
                logger.info(
                    "continuity.auto_response",
                    requester=requester,
                    matched=True,
                )
                return {
                    "action": "auto_response",
                    "message": auto_response,
                    "disclaimer": "Auto-generated response while Tim is unavailable.",
                }

        # Check if this violates boundaries
        if self._violates_boundaries(query):
            self._queue_decision(query, requester, reason="violates_boundaries")
            return {
                "action": "queued",
                "message": (
                    "This request requires Tim's direct approval and has been "
                    "queued for his return. It touches areas outside the system's "
                    "autonomous boundaries."
                ),
            }

        # Queue complex decisions
        self._queue_decision(query, requester, reason="complex_decision")
        return {
            "action": "queued",
            "message": (
                "Your request has been logged and queued for Tim's review. "
                "He will respond when he returns."
            ),
        }

    def get_queued_decisions(self) -> list[dict[str, Any]]:
        """Return all queued decisions awaiting Tim's return."""
        return self._protocol.queued_decisions

    def resolve_decision(self, index: int, resolution: str) -> bool:
        """Resolve a queued decision."""
        if 0 <= index < len(self._protocol.queued_decisions):
            self._protocol.queued_decisions[index]["resolved"] = True
            self._protocol.queued_decisions[index]["resolution"] = resolution
            self._protocol.queued_decisions[index]["resolved_at"] = str(datetime.utcnow())
            return True
        return False

    @staticmethod
    def _match_auto_response(query: str) -> str | None:
        """Match a query against auto-response patterns."""
        query_lower = query.lower()
        for keyword, response in _AUTO_RESPONSE_PATTERNS.items():
            if keyword in query_lower:
                return response
        return None

    def _violates_boundaries(self, query: str) -> bool:
        """Check if a query touches boundary areas."""
        query_lower = query.lower()
        boundary_keywords = {
            "No financial transactions": ["pay", "transfer", "send money", "purchase", "buy"],
            "No client-facing communications": ["send email to client", "respond to client", "client update"],
            "No code deployments": ["deploy", "push to production", "release", "ship"],
            "No hiring decisions": ["hire", "offer", "terminate", "fire"],
            "No contract signing": ["sign", "execute contract", "agree to terms"],
        }

        for boundary, keywords in boundary_keywords.items():
            if boundary in self._protocol.boundaries:
                if any(kw in query_lower for kw in keywords):
                    return True
        return False

    def _queue_decision(self, query: str, requester: str, reason: str) -> None:
        """Add a decision to the queue."""
        self._protocol.queued_decisions.append(
            {
                "query": query,
                "requester": requester,
                "reason": reason,
                "queued_at": str(datetime.utcnow()),
                "resolved": False,
            }
        )
        logger.info(
            "continuity.decision_queued",
            requester=requester,
            reason=reason,
            queue_size=len(self._protocol.queued_decisions),
        )
