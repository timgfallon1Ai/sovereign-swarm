"""ATS learning bridge — converts trade outcomes to SkillPatches.

Receives trade results from ATS (via outcome_reporter.py HTTP POST or
local file reading) and feeds them to the sovereign-swarm FastLearner
for skill patch generation. The trading agent then retrieves these
patches before making future decisions.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def outcome_to_skill_context(outcome: dict[str, Any]) -> dict[str, Any]:
    """Convert an ATS trade outcome into context for skill patch learning.

    Parameters
    ----------
    outcome : dict
        Trade outcome from ATS with keys: sleeve, market_id, outcome, pnl, metadata.

    Returns
    -------
    dict suitable for FastLearner.on_success() or on_failure().
    """
    sleeve = outcome.get("sleeve", "unknown")
    pnl = float(outcome.get("pnl", 0))
    market_id = outcome.get("market_id", "")
    result = outcome.get("outcome", "")
    metadata = outcome.get("metadata", {})

    return {
        "task_type": f"trading_{sleeve}",
        "agent_name": "trading",
        "task_description": f"{sleeve} trade on {market_id}: {result} (PnL: ${pnl:+.2f})",
        "task_keywords": [
            sleeve,
            "trading",
            result,
            market_id.split("_")[0] if "_" in market_id else market_id,
        ],
        "success": pnl >= 0,
        "confidence": metadata.get("confidence", 0.5),
        "context": {
            "sleeve": sleeve,
            "market_id": market_id,
            "pnl": pnl,
            "signals_used": metadata.get("signals", []),
            "swarm_consensus": metadata.get("swarm_consensus", {}),
            "regime": metadata.get("regime", "unknown"),
        },
    }


def process_outcome_batch(outcomes: list[dict[str, Any]]) -> dict[str, Any]:
    """Process a batch of ATS outcomes and return learning summary.

    Can be called by a FastAPI endpoint or a periodic background task.
    """
    wins = sum(1 for o in outcomes if float(o.get("pnl", 0)) >= 0)
    losses = len(outcomes) - wins
    total_pnl = sum(float(o.get("pnl", 0)) for o in outcomes)

    by_sleeve: dict[str, dict[str, Any]] = {}
    for o in outcomes:
        sleeve = o.get("sleeve", "unknown")
        if sleeve not in by_sleeve:
            by_sleeve[sleeve] = {"wins": 0, "losses": 0, "pnl": 0.0, "count": 0}
        s = by_sleeve[sleeve]
        s["count"] += 1
        s["pnl"] += float(o.get("pnl", 0))
        if float(o.get("pnl", 0)) >= 0:
            s["wins"] += 1
        else:
            s["losses"] += 1

    return {
        "total_outcomes": len(outcomes),
        "wins": wins,
        "losses": losses,
        "total_pnl": total_pnl,
        "win_rate": wins / len(outcomes) if outcomes else 0,
        "by_sleeve": by_sleeve,
        "skill_contexts": [outcome_to_skill_context(o) for o in outcomes],
    }
