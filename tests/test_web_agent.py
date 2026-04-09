"""Smoke test for WebAgent.

The backend test needs mlx-vlm + the UI-TARS model, which live in
sovereign-video's venv on this machine. Run it via:

    cd ~/Documents/GitHub/sovereign-video && \
      .venv/bin/python -m pytest \
      ~/Documents/GitHub/sovereign-swarm/tests/test_web_agent.py -v

Or run the __main__ block directly:

    .venv/bin/python ~/Documents/GitHub/sovereign-swarm/tests/test_web_agent.py

The lightweight tests (coordinate parsing, card, intent inference) do NOT
need MLX and run in any venv.
"""
from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path

import pytest

# Allow running this file from either venv by adding the swarm package path.
_SWARM_PKG = Path(__file__).resolve().parents[1]
if str(_SWARM_PKG) not in sys.path:
    sys.path.insert(0, str(_SWARM_PKG))

# structlog is a required dependency of swarm; skip the file if not present
# in the current venv (e.g. running from sovereign-video's venv).
_HAS_STRUCTLOG = importlib.util.find_spec("structlog") is not None
if not _HAS_STRUCTLOG:
    pytest.skip("structlog not installed in this venv", allow_module_level=True)

from sovereign_swarm.protocol.swarm_agent import SwarmAgentRequest  # noqa: E402
from sovereign_swarm.web_agent import UITarsBackend, WebAgent  # noqa: E402
from sovereign_swarm.web_agent.backend import VLMResponse  # noqa: E402


# ---------- Lightweight tests (no MLX needed) ----------

class TestCoordinateParsing:
    def test_box_token_format(self):
        out = UITarsBackend._extract_coordinates(
            "Here is the button <|box_start|>(512, 509)<|box_end|> for you."
        )
        assert out == (512, 509)

    def test_plain_paren_format(self):
        out = UITarsBackend._extract_coordinates("The Sign In button is at (504, 498).")
        assert out == (504, 498)

    def test_no_match_returns_none(self):
        assert UITarsBackend._extract_coordinates("I don't know where it is.") is None

    def test_first_match_wins(self):
        # Plain-paren regex picks up the first pair when no box tokens exist.
        out = UITarsBackend._extract_coordinates("First at (100, 200), then (300, 400).")
        assert out == (100, 200)


class TestAgentCard:
    def test_card_fields(self):
        agent = WebAgent(backend=UITarsBackend())  # backend is not loaded
        card = agent.card
        assert card.name == "web_agent"
        assert "gui" in card.domains
        assert "describe" in card.supported_intents
        assert "locate" in card.supported_intents
        assert "answer" in card.supported_intents


class TestIntentInference:
    @pytest.mark.parametrize(
        "task,expected",
        [
            ("Describe this image", "describe"),
            ("Where is the Sign In button?", "locate"),
            ("Locate the search bar", "locate"),
            ("Click the submit button", "locate"),
            ("What does this page say?", "answer"),
            ("", "describe"),
        ],
    )
    def test_infer_intent(self, task, expected):
        assert WebAgent._infer_intent(task) == expected


class TestExecuteErrorPaths:
    def test_missing_image_param(self):
        agent = WebAgent(backend=UITarsBackend())  # not loaded
        req = SwarmAgentRequest(task="describe", parameters={})
        resp = asyncio.run(agent.execute(req))
        assert resp.status == "error"
        assert "image" in (resp.error or "")


class TestBootstrapRegistry:
    """WebAgent is auto-registered by bootstrap_default_registry()."""

    def test_web_agent_present(self):
        from sovereign_swarm.protocol.registry import bootstrap_default_registry

        reg = bootstrap_default_registry()
        agent = reg.get_agent("web_agent")
        assert agent is not None
        assert isinstance(agent, WebAgent)

    def test_web_agent_card_in_list(self):
        from sovereign_swarm.protocol.registry import bootstrap_default_registry

        reg = bootstrap_default_registry()
        names = {c.name for c in reg.list_agents()}
        assert "web_agent" in names


# ---------- Heavy tests (need MLX + model) ----------

_HAS_MLX = importlib.util.find_spec("mlx_vlm") is not None
_FIXTURES = Path.home() / "Documents/GitHub/sovereign-video/tests/fixtures"
_LOGIN = _FIXTURES / "login_page.png"


@pytest.mark.skipif(not _HAS_MLX, reason="mlx-vlm not installed in this venv")
@pytest.mark.skipif(not _LOGIN.exists(), reason=f"{_LOGIN} fixture missing")
class TestUITarsEndToEnd:
    """Full load + inference. Takes ~10-20s on M4 32GB."""

    def test_describe(self):
        agent = WebAgent()
        req = SwarmAgentRequest(
            task="describe this screenshot",
            parameters={"image": str(_LOGIN), "intent": "describe", "max_tokens": 96},
        )
        resp = asyncio.run(agent.execute(req))
        assert resp.status == "success", resp.error
        assert len(resp.output) > 20
        assert resp.data["tok_s"] > 1.0
        agent.backend.unload()

    def test_locate_sign_in_button(self):
        agent = WebAgent()
        req = SwarmAgentRequest(
            task="locate the Sign In button",
            parameters={
                "image": str(_LOGIN),
                "intent": "locate",
                "element": "blue Sign In button",
                "max_tokens": 32,
            },
        )
        resp = asyncio.run(agent.execute(req))
        assert resp.status == "success", resp.error
        coords = resp.data.get("coordinates")
        assert coords is not None, f"no coords extracted from: {resp.output!r}"
        x, y = coords["x"], coords["y"]
        # True button is (362,484)-(662,534) -> center ~(512, 509).
        # Accept ±60 px tolerance for quantization noise.
        assert 300 <= x <= 720, f"x={x} outside button x-range"
        assert 420 <= y <= 600, f"y={y} outside button y-range"
        agent.backend.unload()


if __name__ == "__main__":
    # Run the smoke tests directly without pytest for quick iteration.
    print("=== lightweight checks ===")
    tp = TestCoordinateParsing()
    tp.test_box_token_format()
    tp.test_plain_paren_format()
    tp.test_no_match_returns_none()
    tp.test_first_match_wins()
    print("✓ coordinate parsing")

    ca = TestAgentCard()
    ca.test_card_fields()
    print("✓ agent card")

    for t, e in [
        ("Describe this image", "describe"),
        ("Where is the Sign In button?", "locate"),
        ("What does this page say?", "answer"),
    ]:
        assert WebAgent._infer_intent(t) == e
    print("✓ intent inference")

    if _HAS_MLX and _LOGIN.exists():
        print("\n=== heavy UI-TARS end-to-end ===")
        e2e = TestUITarsEndToEnd()
        e2e.test_describe()
        print("✓ describe")
        e2e.test_locate_sign_in_button()
        print("✓ locate Sign In button")
    else:
        print("\n(skipping heavy tests: mlx-vlm or fixture missing)")
    print("\nall good.")
