"""Smoke tests for SwarmCoordinator.with_defaults().

Verifies the one-liner factory produces a correctly wired coordinator with
the full default agent lineup, including web_agent.
"""
from __future__ import annotations

import importlib.util
import tempfile
from pathlib import Path

import pytest

_HAS_STRUCTLOG = importlib.util.find_spec("structlog") is not None
if not _HAS_STRUCTLOG:
    pytest.skip("structlog not installed in this venv", allow_module_level=True)

from sovereign_swarm.runtime.coordinator import SwarmCoordinator  # noqa: E402
from sovereign_swarm.web_agent import WebAgent  # noqa: E402


@pytest.fixture
def tmp_checkpoint_db(tmp_path: Path) -> str:
    return str(tmp_path / "checkpoints.db")


class TestWithDefaults:
    def test_builds_without_args(self, tmp_checkpoint_db: str):
        coord = SwarmCoordinator.with_defaults(checkpoint_db=tmp_checkpoint_db)
        assert coord.registry is not None
        assert coord.executor is not None
        assert coord.checkpoint is not None

    def test_executor_shares_registry(self, tmp_checkpoint_db: str):
        coord = SwarmCoordinator.with_defaults(checkpoint_db=tmp_checkpoint_db)
        assert coord.executor.registry is coord.registry

    def test_web_agent_registered(self, tmp_checkpoint_db: str):
        coord = SwarmCoordinator.with_defaults(checkpoint_db=tmp_checkpoint_db)
        agent = coord.registry.get_agent("web_agent")
        assert agent is not None
        assert isinstance(agent, WebAgent)

    def test_multiple_agents_registered(self, tmp_checkpoint_db: str):
        coord = SwarmCoordinator.with_defaults(checkpoint_db=tmp_checkpoint_db)
        cards = coord.registry.list_agents()
        # Should have at least the core lineup — exact count depends on
        # which optional deps are installed, but web_agent + scientist
        # + a handful of others must always be present.
        assert len(cards) >= 5
        names = {c.name for c in cards}
        assert "web_agent" in names

    def test_passes_config(self, tmp_checkpoint_db: str):
        custom = {"coordinator_model": "claude-opus-4-6"}
        coord = SwarmCoordinator.with_defaults(
            checkpoint_db=tmp_checkpoint_db, config=custom
        )
        assert coord._model == "claude-opus-4-6"

    def test_default_checkpoint_db_path(self):
        # Without explicit path, uses data/checkpoints.db in cwd — don't
        # actually write there in the test, just verify construction.
        with tempfile.TemporaryDirectory() as td:
            import os
            old = os.getcwd()
            try:
                os.chdir(td)
                coord = SwarmCoordinator.with_defaults()
                assert coord.checkpoint is not None
            finally:
                os.chdir(old)
