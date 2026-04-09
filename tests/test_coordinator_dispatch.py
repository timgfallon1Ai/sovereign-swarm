"""End-to-end dispatch test for SwarmCoordinator.

Exercises `_decompose_goal` through the real Anthropic API to verify
that the LLM decomposer actually routes vision/GUI goals to web_agent.

Requires ANTHROPIC_API_KEY (loaded from repo .env if present) and network
access. Skipped otherwise.

Run explicitly:
    .venv/bin/python -m pytest tests/test_coordinator_dispatch.py -v -s
"""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import pytest

_HAS_STRUCTLOG = importlib.util.find_spec("structlog") is not None
if not _HAS_STRUCTLOG:
    pytest.skip("structlog not installed in this venv", allow_module_level=True)

# Load .env so local runs don't need the key in the shell environment.
_ENV_FILE = Path(__file__).resolve().parents[1] / ".env"
if _ENV_FILE.exists():
    try:
        from dotenv import load_dotenv

        load_dotenv(_ENV_FILE, override=False)
    except ImportError:
        pass

_HAS_KEY = bool(os.environ.get("ANTHROPIC_API_KEY"))
_HAS_ANTHROPIC = importlib.util.find_spec("anthropic") is not None

pytestmark = [
    pytest.mark.skipif(not _HAS_KEY, reason="ANTHROPIC_API_KEY not set"),
    pytest.mark.skipif(not _HAS_ANTHROPIC, reason="anthropic SDK not installed"),
]

from sovereign_swarm.runtime.coordinator import SwarmCoordinator  # noqa: E402


@pytest.mark.asyncio
async def test_vision_goal_routes_to_web_agent(tmp_path: Path):
    """A vision/GUI goal should be decomposed with at least one web_agent node."""
    coord = SwarmCoordinator.with_defaults(
        checkpoint_db=str(tmp_path / "checkpoints.db"),
        config={"coordinator_model": "claude-haiku-4-5-20251001"},
    )

    graph = await coord._decompose_goal(
        goal=(
            "I have a screenshot of a login page at /tmp/login_page.png. "
            "Find the pixel coordinates of the blue 'Sign In' button so I can "
            "click it programmatically."
        ),
        user_id="test_user",
        conversation_id="test_dispatch",
    )

    assigned = [node.assigned_agent for node in graph.nodes]
    print(f"\ndecomposed assignments: {assigned}")
    assert any(
        a == "web_agent" for a in assigned
    ), f"web_agent not in decomposition: {assigned}"


@pytest.mark.asyncio
async def test_financial_goal_does_not_route_to_web_agent(tmp_path: Path):
    """Negative control: a pure finance goal should NOT be routed to web_agent."""
    coord = SwarmCoordinator.with_defaults(
        checkpoint_db=str(tmp_path / "checkpoints.db"),
        config={"coordinator_model": "claude-haiku-4-5-20251001"},
    )

    graph = await coord._decompose_goal(
        goal=(
            "What is my net worth across ATS, GBB, and GLI accounts "
            "as of the most recent month?"
        ),
        user_id="test_user",
        conversation_id="test_dispatch_neg",
    )

    assigned = [node.assigned_agent for node in graph.nodes]
    print(f"\ndecomposed assignments: {assigned}")
    # Either financial_ops or personal_finance should be the lead — not web_agent.
    assert any(
        a in ("financial_ops", "personal_finance") for a in assigned
    ), f"no finance agent in decomposition: {assigned}"
    assert all(
        a != "web_agent" for a in assigned
    ), f"web_agent wrongly assigned to a finance task: {assigned}"
