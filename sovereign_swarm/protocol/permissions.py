"""Permission management for agent action gating."""

from __future__ import annotations

import re
from typing import Any

import structlog

logger = structlog.get_logger()

# Keywords that trigger approval requirements for financial agents.
FINANCIAL_KEYWORDS: list[str] = [
    "buy",
    "sell",
    "execute",
    "trade",
    "order",
    "liquidate",
    "short",
    "margin",
    "withdraw",
]

DEFAULT_PERMISSIONS: dict[str, dict[str, Any]] = {
    "trading": {
        "level": "requires_approval",
        "keywords": FINANCIAL_KEYWORDS,
        "description": "Trading agent requires approval for financial operations",
    },
}


class PermissionManager:
    """Gate agent actions based on configurable permission rules.

    Default behaviour: the ``trading`` agent requires explicit approval for
    buy/sell/execute/trade actions.  All other agents are auto-approved.
    """

    def __init__(self, permissions: dict[str, dict[str, Any]] | None = None) -> None:
        self._permissions: dict[str, dict[str, Any]] = (
            permissions if permissions is not None else dict(DEFAULT_PERMISSIONS)
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def check_permission(
        self, agent_name: str, action: str, task_text: str
    ) -> tuple[bool, str]:
        """Check whether *agent_name* is allowed to perform *action*.

        Returns ``(allowed, reason)`` where *allowed* is ``False`` when
        human approval is required.
        """
        agent_key = agent_name.lower().strip()
        rule = self._permissions.get(agent_key)

        if rule is None:
            # No explicit rule -> auto-approved
            return True, "auto_approved"

        level = rule.get("level", "auto")

        if level == "auto":
            return True, "auto_approved"

        if level in ("requires_approval", "manual_only"):
            keywords = rule.get("keywords", [])
            if keywords and self._matches_keywords(task_text, keywords):
                reason = (
                    f"Agent '{agent_name}' requires approval: "
                    f"task contains restricted keyword(s)"
                )
                logger.info(
                    "permission.denied",
                    agent=agent_name,
                    action=action,
                    reason=reason,
                )
                return False, reason

            # Keywords defined but none matched -> auto
            if keywords:
                return True, "auto_approved_no_keyword_match"

            # No keywords defined but level is requires_approval -> block all
            reason = f"Agent '{agent_name}' requires approval for all actions"
            return False, reason

        if level == "auto_notify":
            # Allowed, but the caller should log/notify
            return True, "auto_notify"

        # Unknown level defaults to auto
        return True, "auto_approved"

    def require_elevated(self, agent_name: str) -> bool:
        """Return True if the agent always requires elevated approval."""
        agent_key = agent_name.lower().strip()
        rule = self._permissions.get(agent_key)
        if rule is None:
            return False
        return rule.get("level") in ("requires_approval", "manual_only")

    # ------------------------------------------------------------------
    # Mutation helpers (for runtime reconfiguration)
    # ------------------------------------------------------------------

    def set_permission(self, agent_name: str, rule: dict[str, Any]) -> None:
        """Add or update a permission rule for an agent."""
        self._permissions[agent_name.lower().strip()] = rule

    def remove_permission(self, agent_name: str) -> None:
        """Remove a permission rule, reverting agent to auto-approved."""
        self._permissions.pop(agent_name.lower().strip(), None)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    def _matches_keywords(text: str, keywords: list[str]) -> bool:
        """Return True if *text* contains any of the *keywords* (word-boundary match)."""
        text_lower = text.lower()
        for kw in keywords:
            if re.search(rf"\b{re.escape(kw)}\b", text_lower):
                return True
        return False
