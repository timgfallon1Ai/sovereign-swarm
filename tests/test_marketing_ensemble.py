"""Tests for the Sovereign marketing ensemble (ATX Mats / GBB / GLI).

Covers:
- Tenant brand registry has all 3 expected tenants with correct shape
- Brand lookup by key + unknown-key error handling
- Ensemble dispatch via a stub OpenMontage registry (no real TTS/video)
- Stage-level failure isolation (narration fails → video still runs,
  status reflects "partial")
- Manifest written to the output dir as JSON
- MarketingAgent produce_campaign happy path
- MarketingAgent list_tenants + get_brand intents
- MarketingAgent registered via bootstrap_default_registry()
"""

from __future__ import annotations

import asyncio
import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from sovereign_swarm.marketing import (
    MarketingAgent,
    MarketingCampaignRequest,
    SovereignMarketingEnsemble,
    TENANTS,
    get_brand,
)
from sovereign_swarm.protocol.swarm_agent import SwarmAgentRequest


# ---------- Brand registry ----------


class TestTenantBrands:
    def test_all_tenants_present(self):
        assert {"atx_mats", "gbb", "gli", "sovereign"} <= set(TENANTS.keys())

    def test_each_brand_has_required_fields(self):
        for key, brand in TENANTS.items():
            assert brand.key == key
            assert brand.display_name
            assert brand.tagline
            assert brand.one_liner
            assert brand.target_audience
            assert brand.voice_name  # must match a VibeVoice preset
            assert brand.negative_prompt
            assert len(brand.palette) >= 3
            assert len(brand.tone_keywords) >= 3

    def test_get_brand_happy_path(self):
        brand = get_brand("atx_mats")
        assert brand.display_name == "ATX Mats"
        assert brand.voice_name == "Davis"

    def test_get_brand_unknown_raises(self):
        with pytest.raises(KeyError, match="Unknown marketing tenant"):
            get_brand("not_a_tenant")


# ---------- Stub OpenMontage registry for ensemble tests ----------


class _StubTool:
    def __init__(self, success: bool = True, error: str | None = None, data: dict[str, Any] | None = None):
        self.success = success
        self.error = error
        self.data_template = data or {}
        self.calls: list[dict[str, Any]] = []

    def execute(self, inputs: dict[str, Any]) -> Any:
        self.calls.append(inputs)
        # Simulate the tool writing its output file
        out_path = Path(inputs.get("output_path", ""))
        if self.success and out_path:
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_bytes(b"\x00" * 1024)
        return SimpleNamespace(
            success=self.success,
            error=self.error,
            data={**self.data_template, "provider": "stub"},
        )


class _StubRegistry:
    def __init__(self, tts_tool: _StubTool, video_tool: _StubTool):
        self._tools = {
            "vibevoice_tts": tts_tool,
            "wan22_mlx_video": video_tool,
        }

    def get(self, name: str) -> _StubTool | None:
        return self._tools.get(name)


@pytest.fixture
def stub_loader():
    """Build a registry loader closure for the ensemble constructor."""

    def _make(tts: _StubTool, video: _StubTool):
        reg = _StubRegistry(tts, video)
        return lambda: reg

    return _make


# ---------- Ensemble dispatch ----------


class TestEnsembleRun:
    def test_happy_path_all_stages_success(self, tmp_path, stub_loader):
        tts = _StubTool(
            success=True,
            data={
                "rtf": 1.22,
                "audio_duration_s": 12.5,
                "sample_rate_hz": 24000,
                "model": "vibevoice-realtime-0.5b",
            },
        )
        video = _StubTool(
            success=True,
            data={
                "width": 1280,
                "height": 704,
                "num_frames": 97,
                "steps": 30,
                "seed": 7,
                "model": "wan22-mlx",
                "probe_duration": "4.04",
                "probe_codec_name": "h264",
            },
        )
        ensemble = SovereignMarketingEnsemble(
            output_root=tmp_path, registry_loader=stub_loader(tts, video)
        )

        req = MarketingCampaignRequest(
            tenant="atx_mats",
            campaign_id="showroom-loop-v1",
            narration_text=(
                "ATX Mats: the flooring that outlasts the warranty. "
                "Engineered for warehouses, gyms, and showrooms that "
                "need to take a decade of abuse."
            ),
            video_prompt=(
                "cinematic showroom turntable shot of a golden ATX "
                "Mats flooring sample, studio lighting, shallow DOF"
            ),
        )

        result = ensemble.run(req)
        assert result.status in {"success", "partial"}  # mux may skip if no ffmpeg
        assert result.tenant == "atx_mats"
        assert result.campaign_id == "showroom-loop-v1"
        assert "narration" in result.artifacts
        assert "video" in result.artifacts
        # Stage logs
        names = [s.stage for s in result.stages]
        assert names == ["narration", "video", "mux"]
        # Narration stage carried TTS metadata through
        narr_stage = result.stages[0]
        assert narr_stage.status == "success"
        assert narr_stage.data["rtf"] == 1.22
        assert narr_stage.data["audio_duration_s"] == 12.5
        # Video stage
        vid_stage = result.stages[1]
        assert vid_stage.status == "success"
        assert vid_stage.data["width"] == 1280
        # Manifest written
        manifest_files = list(Path(result.output_dir).glob("manifest.json"))
        assert len(manifest_files) == 1
        manifest = json.loads(manifest_files[0].read_text())
        assert manifest["tenant"] == "atx_mats"
        assert manifest["brand"]["voice_name"] == "Davis"

    def test_tts_passes_correct_brand_params(self, tmp_path, stub_loader):
        tts = _StubTool(success=True)
        video = _StubTool(success=True)
        ensemble = SovereignMarketingEnsemble(
            output_root=tmp_path, registry_loader=stub_loader(tts, video)
        )
        req = MarketingCampaignRequest(
            tenant="gbb",
            campaign_id="test-gbb",
            narration_text="test text",
            video_prompt="test prompt",
        )
        ensemble.run(req)
        assert len(tts.calls) == 1
        call = tts.calls[0]
        assert call["speaker_name"] == "Frank"  # GBB's brand voice
        assert call["text"] == "test text"

    def test_video_passes_negative_prompt_from_brand(self, tmp_path, stub_loader):
        tts = _StubTool(success=True)
        video = _StubTool(success=True)
        ensemble = SovereignMarketingEnsemble(
            output_root=tmp_path, registry_loader=stub_loader(tts, video)
        )
        req = MarketingCampaignRequest(
            tenant="gli",
            campaign_id="test-gli",
            narration_text="t",
            video_prompt="p",
            extra_negative_prompt="bad hands",
        )
        ensemble.run(req)
        call = video.calls[0]
        assert "marijuana leaf cliche" in call["negative_prompt"]  # from GLI brand
        assert "bad hands" in call["negative_prompt"]  # extras appended

    def test_narration_failure_partial_status(self, tmp_path, stub_loader):
        tts = _StubTool(success=False, error="vibevoice venv missing")
        video = _StubTool(success=True)
        ensemble = SovereignMarketingEnsemble(
            output_root=tmp_path, registry_loader=stub_loader(tts, video)
        )
        req = MarketingCampaignRequest(
            tenant="atx_mats",
            campaign_id="fail-tts",
            narration_text="n",
            video_prompt="p",
        )
        result = ensemble.run(req)
        assert result.stages[0].status == "error"
        assert "narration" not in result.artifacts
        # Video still ran
        assert result.stages[1].status == "success"
        assert "video" in result.artifacts
        # Mux skipped because narration is missing
        assert result.stages[2].status == "skipped"
        assert result.status == "partial"

    def test_unknown_tenant_raises_keyerror(self, tmp_path, stub_loader):
        tts = _StubTool(success=True)
        video = _StubTool(success=True)
        ensemble = SovereignMarketingEnsemble(
            output_root=tmp_path, registry_loader=stub_loader(tts, video)
        )
        req = MarketingCampaignRequest(
            tenant="invalid",
            campaign_id="x",
            narration_text="t",
            video_prompt="p",
        )
        with pytest.raises(KeyError):
            ensemble.run(req)

    def test_resolution_override(self, tmp_path, stub_loader):
        tts = _StubTool(success=True)
        video = _StubTool(success=True)
        ensemble = SovereignMarketingEnsemble(
            output_root=tmp_path, registry_loader=stub_loader(tts, video)
        )
        req = MarketingCampaignRequest(
            tenant="atx_mats",
            campaign_id="res-override",
            narration_text="n",
            video_prompt="p",
            resolution=(512, 288),
            num_frames=25,
            steps=4,
        )
        ensemble.run(req)
        call = video.calls[0]
        assert call["width"] == 512
        assert call["height"] == 288
        assert call["num_frames"] == 25
        assert call["steps"] == 4


# ---------- MarketingAgent (swarm wrapper) ----------


class TestMarketingAgent:
    def test_list_tenants(self, tmp_path, stub_loader):
        tts = _StubTool(success=True)
        video = _StubTool(success=True)
        ensemble = SovereignMarketingEnsemble(
            output_root=tmp_path, registry_loader=stub_loader(tts, video)
        )
        agent = MarketingAgent(ensemble=ensemble)
        req = SwarmAgentRequest(task="list all tenants", parameters={"intent": "list_tenants"})
        resp = asyncio.run(agent.execute(req))
        assert resp.status == "success"
        assert {"atx_mats", "gbb", "gli", "sovereign"} <= set(resp.data["tenants"].keys())

    def test_get_brand(self, tmp_path, stub_loader):
        tts = _StubTool(success=True)
        video = _StubTool(success=True)
        ensemble = SovereignMarketingEnsemble(
            output_root=tmp_path, registry_loader=stub_loader(tts, video)
        )
        agent = MarketingAgent(ensemble=ensemble)
        req = SwarmAgentRequest(
            task="get atx brand", parameters={"intent": "get_brand", "tenant": "atx_mats"}
        )
        resp = asyncio.run(agent.execute(req))
        assert resp.status == "success"
        assert resp.data["display_name"] == "ATX Mats"
        assert resp.data["voice_name"] == "Davis"
        assert "practical" in resp.data["tone_keywords"]

    def test_produce_campaign(self, tmp_path, stub_loader):
        tts = _StubTool(success=True, data={"rtf": 1.1})
        video = _StubTool(success=True, data={"width": 1280, "height": 704})
        ensemble = SovereignMarketingEnsemble(
            output_root=tmp_path, registry_loader=stub_loader(tts, video)
        )
        agent = MarketingAgent(ensemble=ensemble)
        req = SwarmAgentRequest(
            task="produce ATX Mats showroom video",
            parameters={
                "intent": "produce_campaign",
                "tenant": "atx_mats",
                "campaign_id": "spring-launch",
                "narration_text": "Spring flooring launch narration.",
                "video_prompt": "A spring-lit showroom with golden flooring samples.",
            },
        )
        resp = asyncio.run(agent.execute(req))
        assert resp.status == "success"
        assert resp.data["tenant"] == "atx_mats"
        assert resp.data["campaign_id"] == "spring-launch"
        assert "narration" in resp.data["artifacts"]
        assert "video" in resp.data["artifacts"]

    def test_produce_campaign_missing_params(self, tmp_path, stub_loader):
        tts = _StubTool(success=True)
        video = _StubTool(success=True)
        ensemble = SovereignMarketingEnsemble(
            output_root=tmp_path, registry_loader=stub_loader(tts, video)
        )
        agent = MarketingAgent(ensemble=ensemble)
        req = SwarmAgentRequest(
            task="produce",
            parameters={"intent": "produce_campaign", "tenant": "atx_mats"},
        )
        resp = asyncio.run(agent.execute(req))
        assert resp.status == "error"
        assert "campaign_id" in resp.error

    def test_unknown_intent(self, tmp_path, stub_loader):
        tts = _StubTool(success=True)
        video = _StubTool(success=True)
        ensemble = SovereignMarketingEnsemble(
            output_root=tmp_path, registry_loader=stub_loader(tts, video)
        )
        agent = MarketingAgent(ensemble=ensemble)
        req = SwarmAgentRequest(task="x", parameters={"intent": "rebrand_everything"})
        resp = asyncio.run(agent.execute(req))
        assert resp.status == "error"


# ---------- Bootstrap registry ----------


class TestBootstrapRegistry:
    def test_marketing_agent_registered(self):
        from sovereign_swarm.protocol.registry import bootstrap_default_registry

        reg = bootstrap_default_registry()
        agent = reg.get_agent("marketing")
        assert agent is not None
        assert isinstance(agent, MarketingAgent)
