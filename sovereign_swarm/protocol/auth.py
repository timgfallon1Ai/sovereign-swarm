"""HMAC-SHA256 message authentication for inter-agent messages."""

from __future__ import annotations

import hashlib
import hmac
import json

import structlog

from sovereign_swarm.protocol.models import AgentMessage

logger = structlog.get_logger()


class MessageAuthenticator:
    """Sign and verify AgentMessage instances using HMAC-SHA256."""

    def __init__(self, secret_key: str) -> None:
        if not secret_key:
            raise ValueError("secret_key must be a non-empty string")
        self._key = secret_key.encode("utf-8")

    def sign(self, message: AgentMessage) -> AgentMessage:
        """Compute HMAC-SHA256 of the payload and set the signature field.

        Returns the same message instance (mutated) for chaining convenience.
        """
        digest = self._compute_digest(message)
        message.signature = digest
        return message

    def verify(self, message: AgentMessage) -> bool:
        """Recompute the HMAC and compare with the stored signature."""
        if not message.signature:
            logger.warning("auth.verify.missing_signature", message_id=message.id)
            return False

        expected = self._compute_digest(message)
        valid = hmac.compare_digest(expected, message.signature)

        if not valid:
            logger.warning(
                "auth.verify.failed",
                message_id=message.id,
                from_agent=message.from_agent,
            )

        return valid

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _compute_digest(self, message: AgentMessage) -> str:
        """Produce a hex digest from the message payload, excluding signature."""
        # Serialize payload deterministically
        payload_bytes = json.dumps(
            message.payload, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")

        # Include envelope fields for additional tamper resistance
        canonical = (
            f"{message.id}|{message.from_agent}|{message.to_agent}|"
            f"{message.message_type}|{message.graph_id}|{message.node_id}|"
            f"{message.timestamp.isoformat()}"
        ).encode("utf-8")

        digest = hmac.new(self._key, canonical + payload_bytes, hashlib.sha256)
        return digest.hexdigest()
