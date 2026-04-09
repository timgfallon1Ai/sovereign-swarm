"""Phase 2 marketing ensemble tests.

Covers the six Phase 2 extensions:
  1. Remotion composer wrapper (remotion_compose.py)
  2. FLUX still-image stage (stills.py)
  3. Claude script generation (script_gen.py)
  4. UI-TARS thumbnail QA (thumbnail_qa.py)
  5. CampaignBrief schema (brief.py)
  6. Publish gate (publish_gate.py)

Plus end-to-end ``SovereignMarketingEnsemble.run_brief()`` happy path
and MarketingAgent produce_campaign_from_brief intent.

All external dependencies (Claude API, infsh CLI, ffmpeg, UI-TARS,
Remotion, Node) are stubbed so tests are fast and deterministic.
"""

from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from sovereign_swarm.marketing import (
    CampaignBrief,
    CampaignObjective,
    FluxStillsStage,
    MarketingAgent,
    MarketingScriptGenerator,
    Platform,
    PublishGate,
    RemotionComposerStage,
    ScriptResult,
    SovereignMarketingEnsemble,
    ThumbnailQAStage,
    get_brand,
)
from sovereign_swarm.marketing.stills import (
    StillResult,
    StillsResult,
    _extract_output_path,
)
from sovereign_swarm.marketing.remotion_compose import RemotionResult
from sovereign_swarm.marketing.thumbnail_qa import (
    ThumbnailQAResult,
    _parse_qa_response,
)
from sovereign_swarm.protocol.swarm_agent import SwarmAgentRequest


# ---------- CampaignBrief (#5) ----------


class TestCampaignBrief:
    def _minimal(self, **overrides):
        base = dict(
            tenant="atx_mats",
            campaign_id="test-001",
            subject="new gym flooring line",
            audience="commercial gym owners",
            objective=CampaignObjective.LAUNCH,
            key_message="Outlasts the warranty",
            call_to_action="Request a sample",
        )
        base.update(overrides)
        return CampaignBrief(**base)

    def test_minimal_brief(self):
        brief = self._minimal()
        assert brief.tenant == "atx_mats"
        assert brief.objective == CampaignObjective.LAUNCH
        assert brief.enable_thumbnail_qa is True
        assert brief.require_publish_approval is True
        assert brief.num_stills == 0

    def test_brand_prompt_block(self):
        brief = self._minimal(
            constraints=("no medical claims", "no pricing"),
            platforms=(Platform.YOUTUBE_SHORT, Platform.LINKEDIN),
            duration_seconds=30,
            notes="Focus on load rating",
        )
        block = brief.brand_prompt_block()
        assert "Subject: new gym flooring line" in block
        assert "no medical claims" in block
        assert "youtube_short" in block
        assert "~30 seconds" in block
        assert "Focus on load rating" in block

    def test_from_dict_roundtrip(self):
        data = {
            "tenant": "gli",
            "campaign_id": "spring-grow",
            "subject": "new 730W LED bar",
            "audience": "commercial cultivators",
            "objective": "conversion",
            "key_message": "PAR up 18%",
            "call_to_action": "Shop the bar",
            "constraints": ["no legal-gray claims"],
            "platforms": ["instagram_reel", "tiktok"],
            "duration_seconds": 45,
            "num_stills": 3,
            "enable_remotion": True,
            "resolution": [1280, 704],
        }
        brief = CampaignBrief.from_dict(data)
        assert brief.tenant == "gli"
        assert brief.objective == CampaignObjective.CONVERSION
        assert Platform.INSTAGRAM_REEL in brief.platforms
        assert brief.num_stills == 3
        assert brief.enable_remotion is True
        assert brief.resolution == (1280, 704)

    def test_to_dict_converts_enums(self):
        brief = self._minimal(
            platforms=(Platform.LINKEDIN,),
        )
        d = brief.to_dict()
        assert d["objective"] == "launch"
        assert d["platforms"] == ["linkedin"]


# ---------- Script generation (#3) ----------


class _StubAsyncAnthropic:
    """Stub AsyncAnthropic client that returns a pre-fab response."""

    def __init__(self, payload: str, raise_exc: Exception | None = None):
        self.payload = payload
        self.raise_exc = raise_exc
        self.calls = []

        async def _create(**kwargs):
            self.calls.append(kwargs)
            if self.raise_exc is not None:
                raise self.raise_exc
            return SimpleNamespace(
                content=[SimpleNamespace(type="text", text=payload)],
                usage=SimpleNamespace(input_tokens=100, output_tokens=80),
            )

        self.messages = SimpleNamespace(create=_create)


def _valid_script_payload():
    return json.dumps(
        {
            "narration_text": (
                "By the end of this thirty seconds you will know exactly why "
                "ATX Mats outlast every warranty in commercial flooring. We "
                "engineer every mat for a decade of abuse."
            ),
            "video_prompt": (
                "cinematic macro shot of golden ATX Mats gym flooring under "
                "studio lighting, navy #1a2332 background, slow dolly-in"
            ),
            "still_prompts": [
                "hero shot of golden flooring, brass accent, cream backdrop",
                "top-down view of weight-dropped mat, slate texture detail",
            ],
            "captions": [
                "Engineered in Austin",
                "Manufactured in Shanghai",
                "Built to outlast the warranty",
            ],
            "rationale": "Informing objective with a strong opening promise",
            "warnings": [],
        }
    )


class TestMarketingScriptGenerator:
    def _brief(self):
        return CampaignBrief(
            tenant="atx_mats",
            campaign_id="test",
            subject="gym flooring",
            audience="commercial gym owners",
            objective=CampaignObjective.AWARENESS,
            key_message="Outlasts the warranty",
            call_to_action="Request a sample",
            num_stills=2,
            enable_remotion=True,
        )

    def test_disabled_mode(self):
        gen = MarketingScriptGenerator(client=None)
        r = asyncio.run(gen.generate(self._brief(), get_brand("atx_mats")))
        assert r.status == "disabled"
        assert r.success is False
        assert "None" in (r.error or "")

    def test_happy_path(self):
        client = _StubAsyncAnthropic(_valid_script_payload())
        gen = MarketingScriptGenerator(client=client, model="claude-haiku-4-5-20251001")
        r = asyncio.run(gen.generate(self._brief(), get_brand("atx_mats")))
        assert r.status == "success"
        assert r.success is True
        assert r.narration_text and "thirty seconds" in r.narration_text
        assert r.video_prompt and "cinematic" in r.video_prompt
        assert len(r.still_prompts) == 2
        assert len(r.captions) == 3
        assert r.input_tokens == 100
        assert r.output_tokens == 80
        # Prompt included tenant brand info
        call = client.calls[0]
        user_msg = call["messages"][0]["content"]
        assert "ATX Mats" in user_msg
        assert "Davis" in user_msg  # voice name
        assert "practical" in user_msg  # tone keyword

    def test_api_error(self):
        client = _StubAsyncAnthropic("", raise_exc=RuntimeError("net down"))
        gen = MarketingScriptGenerator(client=client)
        r = asyncio.run(gen.generate(self._brief(), get_brand("atx_mats")))
        assert r.status == "api_error"
        assert "net down" in (r.error or "")

    def test_parse_error_empty(self):
        client = _StubAsyncAnthropic("")
        gen = MarketingScriptGenerator(client=client)
        r = asyncio.run(gen.generate(self._brief(), get_brand("atx_mats")))
        assert r.status == "parse_error"

    def test_parse_error_malformed(self):
        client = _StubAsyncAnthropic("not json at all")
        gen = MarketingScriptGenerator(client=client)
        r = asyncio.run(gen.generate(self._brief(), get_brand("atx_mats")))
        assert r.status == "parse_error"

    def test_validation_missing_required_field(self):
        bad = json.dumps({"video_prompt": "x"})  # missing narration_text
        client = _StubAsyncAnthropic(bad)
        gen = MarketingScriptGenerator(client=client)
        r = asyncio.run(gen.generate(self._brief(), get_brand("atx_mats")))
        assert r.status == "parse_error"
        assert "narration_text" in (r.error or "")


# ---------- FLUX stills stage (#2) ----------


class TestFluxStillsStage:
    def test_no_prompts_is_skipped(self, tmp_path):
        stage = FluxStillsStage()
        r = stage.run(prompts=[], output_dir=tmp_path)
        assert r.status == "skipped"

    def test_binary_missing_is_disabled(self, tmp_path, monkeypatch):
        monkeypatch.setattr(shutil, "which", lambda _: None)
        stage = FluxStillsStage(binary="infsh_not_installed")
        r = stage.run(prompts=["a"], output_dir=tmp_path)
        assert r.status == "disabled"
        assert "ai-image-generation" in (r.error or "")

    def test_command_shape_with_stub_subprocess(self, tmp_path, monkeypatch):
        monkeypatch.setattr(shutil, "which", lambda b: "/fake/infsh")
        captured = []

        def fake_run(cmd, **kwargs):
            captured.append(cmd)
            # Honor the output_path hint so the stage sees the file on disk
            input_idx = cmd.index("--input") + 1
            payload = json.loads(cmd[input_idx])
            Path(payload["output_path"]).write_bytes(b"\x89PNG" + b"\x00" * 100)
            return SimpleNamespace(returncode=0, stdout="done", stderr="")

        stage = FluxStillsStage(
            binary="/fake/infsh",
            negative_prompt="low quality",
        )
        with patch("subprocess.run", side_effect=fake_run):
            r = stage.run(
                prompts=["first prompt", "second prompt"],
                output_dir=tmp_path,
                brand_negative_prompt="cartoon",
            )
        assert r.status == "success"
        assert r.success_count == 2
        assert len(captured) == 2
        first_cmd = captured[0]
        assert first_cmd[0] == "/fake/infsh"
        assert "app" in first_cmd and "run" in first_cmd
        assert first_cmd[first_cmd.index("--input") + 1]  # has a payload
        payload = json.loads(first_cmd[first_cmd.index("--input") + 1])
        assert payload["prompt"] == "first prompt"
        assert "cartoon" in payload["negative_prompt"]
        assert "low quality" in payload["negative_prompt"]

    def test_subprocess_failure_marks_error(self, tmp_path, monkeypatch):
        monkeypatch.setattr(shutil, "which", lambda b: "/fake/infsh")

        def fake_run(cmd, **kwargs):
            return SimpleNamespace(
                returncode=1, stdout="", stderr="quota exceeded"
            )

        stage = FluxStillsStage(binary="/fake/infsh")
        with patch("subprocess.run", side_effect=fake_run):
            r = stage.run(prompts=["p"], output_dir=tmp_path)
        assert r.status == "error"
        assert "quota exceeded" in (r.stills[0].error or "")

    def test_extract_output_path_from_json(self):
        assert _extract_output_path('{"output": "/tmp/x.png"}') == "/tmp/x.png"
        assert _extract_output_path('{"url": "https://x.y/z.jpg"}') == "https://x.y/z.jpg"

    def test_extract_output_path_from_plain_url(self):
        out = _extract_output_path("done! see https://cdn.inference.sh/foo.png")
        assert out == "https://cdn.inference.sh/foo.png"

    def test_extract_output_path_none(self):
        assert _extract_output_path("") is None
        assert _extract_output_path("nothing useful here") is None


# ---------- Thumbnail QA (#4) ----------


class TestThumbnailQA:
    def test_parse_qa_response_ok(self):
        text = (
            "STATUS: OK\nISSUES: none\nCONFIDENCE: 0.92\n"
            "Everything looks on-brand."
        )
        r = _parse_qa_response(text)
        assert r["status"] == "success"
        assert r["issues"] == []
        assert r["confidence"] == 0.92

    def test_parse_qa_response_flagged(self):
        text = "STATUS: FLAGGED\nISSUES: watermark, blurry text\nCONFIDENCE: 0.3"
        r = _parse_qa_response(text)
        assert r["status"] == "flagged"
        assert "watermark" in r["issues"]
        assert "blurry text" in r["issues"]
        assert r["confidence"] == 0.3

    def test_parse_qa_response_loose_format(self):
        text = "Everything looks good to me, all clear."
        r = _parse_qa_response(text)
        assert r["status"] == "success"

    def test_parse_qa_response_empty_defaults_flagged(self):
        r = _parse_qa_response("")
        assert r["status"] == "flagged"
        assert r["confidence"] == 0.5

    def test_missing_video_returns_error(self, tmp_path):
        stage = ThumbnailQAStage()
        r = stage.run(
            video_path=tmp_path / "nope.mp4",
            output_dir=tmp_path,
            brand_display_name="X",
            brand_negative_prompt="",
        )
        assert r.status == "error"

    def test_ffmpeg_missing_skips(self, tmp_path, monkeypatch):
        monkeypatch.setattr(shutil, "which", lambda _: None)
        video = tmp_path / "v.mp4"
        video.write_bytes(b"\x00" * 100)
        stage = ThumbnailQAStage(ffmpeg_binary="ffmpeg_missing")
        r = stage.run(
            video_path=video,
            output_dir=tmp_path,
            brand_display_name="X",
            brand_negative_prompt="",
        )
        assert r.status == "skipped"

    def test_backend_ok_returns_structured_result(self, tmp_path, monkeypatch):
        video = tmp_path / "v.mp4"
        video.write_bytes(b"\x00" * 100)

        # Stub ffmpeg to just touch the thumbnail
        def fake_run(cmd, **kwargs):
            out_idx = len(cmd) - 1
            Path(cmd[out_idx]).write_bytes(b"\x89PNG")
            return SimpleNamespace(returncode=0, stdout="", stderr="")

        class _StubBackend:
            def answer(self, image_path, prompt, max_tokens=256):
                return SimpleNamespace(
                    text="STATUS: OK\nISSUES: none\nCONFIDENCE: 0.95",
                    model="ui-tars-stub",
                )

        stage = ThumbnailQAStage(backend=_StubBackend())
        with patch("subprocess.run", side_effect=fake_run), patch(
            "shutil.which", return_value="/usr/bin/ffmpeg"
        ):
            r = stage.run(
                video_path=video,
                output_dir=tmp_path,
                brand_display_name="ATX Mats",
                brand_negative_prompt="blurry, watermark",
            )
        assert r.status == "success"
        assert r.confidence == 0.95
        assert r.thumbnail_path is not None


# ---------- Remotion composer (#1) ----------


class TestRemotionComposer:
    def test_unavailable_skipped(self, tmp_path):
        stage = RemotionComposerStage(composer_dir=str(tmp_path / "nowhere"))
        video = tmp_path / "v.mp4"
        video.write_bytes(b"\x00")
        audio = tmp_path / "a.wav"
        audio.write_bytes(b"\x00")
        r = stage.run(
            video_path=video,
            audio_path=audio,
            output_path=tmp_path / "out.mp4",
            brand=SimpleNamespace(palette=("#000",), display_name="X", tagline=""),
        )
        assert r.status == "skipped"

    def test_build_props_shape(self, tmp_path):
        stage = RemotionComposerStage()
        props = stage._build_props(
            video_path=tmp_path / "v.mp4",
            audio_path=tmp_path / "a.wav",
            brand=SimpleNamespace(
                palette=("#000", "#fff"),
                display_name="ATX Mats",
                tagline="Outlasts the warranty",
            ),
            captions=["cap1", "cap2", "cap3"],
            still_paths=[str(tmp_path / "s1.png"), str(tmp_path / "s2.png")],
            title_text=None,
        )
        assert props["brand_name"] == "ATX Mats"
        assert props["palette"] == ["#000", "#fff"]
        assert props["audio"]["src"] == str(tmp_path / "a.wav")
        # cuts: primary video + 2 image cuts
        assert len(props["cuts"]) == 3
        assert props["cuts"][0]["type"] == "video"
        assert props["cuts"][1]["type"] == "image"
        # captions
        assert len(props["captions"]) == 3
        assert props["captions"][0]["text"] == "cap1"
        # hero title overlay derived from brand
        assert any(o.get("kind") == "hero_title" for o in props["overlays"])

    def test_command_shape_with_stub_subprocess(self, tmp_path, monkeypatch):
        composer_dir = tmp_path / "remotion-composer"
        (composer_dir / "node_modules").mkdir(parents=True)
        video = tmp_path / "v.mp4"
        video.write_bytes(b"\x00")
        audio = tmp_path / "a.wav"
        audio.write_bytes(b"\x00")
        out = tmp_path / "final.mp4"

        def fake_run(cmd, **kwargs):
            # Simulate Remotion writing the output
            Path(cmd[6]).write_bytes(b"\x00" * 2048)
            return SimpleNamespace(returncode=0, stdout="", stderr="")

        with patch("shutil.which", return_value="/fake/npx"), patch(
            "subprocess.run", side_effect=fake_run
        ):
            stage = RemotionComposerStage(composer_dir=str(composer_dir))
            r = stage.run(
                video_path=video,
                audio_path=audio,
                output_path=out,
                brand=SimpleNamespace(
                    palette=("#000",), display_name="X", tagline=""
                ),
                captions=["x"],
            )
        assert r.status == "success"
        assert out.exists()
        # props file also written
        assert (out.parent / "remotion_props.json").exists()


# ---------- Publish gate (#6) ----------


class TestPublishGate:
    def test_request_approval_writes_files(self, tmp_path):
        gate = PublishGate()
        req = gate.request_approval(
            output_dir=tmp_path,
            tenant="atx_mats",
            campaign_id="c1",
            artifacts={"final": str(tmp_path / "final.mp4")},
            platforms=["youtube_short", "linkedin"],
            owner="tim",
        )
        assert len(req.approval_token) > 16
        assert (tmp_path / "publish_request.json").exists()
        assert (tmp_path / "APPROVAL_INSTRUCTIONS.md").exists()
        parsed = json.loads((tmp_path / "publish_request.json").read_text())
        assert parsed["tenant"] == "atx_mats"
        assert "youtube_short" in parsed["platforms"]

    def test_check_approval_pending(self, tmp_path):
        gate = PublishGate()
        req = gate.request_approval(
            output_dir=tmp_path,
            tenant="gbb",
            campaign_id="c2",
            artifacts={},
        )
        state = gate.check_approval(tmp_path, req)
        assert state.state == "pending"

    def test_check_approval_approved(self, tmp_path):
        gate = PublishGate()
        req = gate.request_approval(
            output_dir=tmp_path,
            tenant="gli",
            campaign_id="c3",
            artifacts={},
        )
        (tmp_path / "approved.token").write_text(req.approval_token)
        state = gate.check_approval(tmp_path, req)
        assert state.state == "approved"

    def test_check_approval_rejected(self, tmp_path):
        gate = PublishGate()
        req = gate.request_approval(
            output_dir=tmp_path,
            tenant="atx_mats",
            campaign_id="c4",
            artifacts={},
        )
        (tmp_path / "rejected.txt").write_text("too hyped")
        state = gate.check_approval(tmp_path, req)
        assert state.state == "rejected"
        assert "too hyped" in (state.rejection_reason or "")

    def test_approval_token_mismatch_is_rejected(self, tmp_path):
        gate = PublishGate()
        req = gate.request_approval(
            output_dir=tmp_path,
            tenant="atx_mats",
            campaign_id="c5",
            artifacts={},
        )
        (tmp_path / "approved.token").write_text("wrong-token")
        state = gate.check_approval(tmp_path, req)
        assert state.state == "rejected"
        assert "token mismatch" in (state.rejection_reason or "")

    def test_replay_preserves_token(self, tmp_path):
        gate = PublishGate()
        req1 = gate.request_approval(
            output_dir=tmp_path,
            tenant="atx_mats",
            campaign_id="c6",
            artifacts={},
        )
        req2 = gate.request_approval(
            output_dir=tmp_path,
            tenant="atx_mats",
            campaign_id="c6",
            artifacts={},
        )
        assert req1.approval_token == req2.approval_token


# ---------- Full ensemble.run_brief() integration ----------


class _StubVibeVoiceTool:
    def execute(self, inputs):
        Path(inputs["output_path"]).write_bytes(b"RIFF" + b"\x00" * 256)
        return SimpleNamespace(
            success=True,
            error=None,
            data={
                "provider": "stub-vibevoice",
                "model": "vibevoice-realtime-0.5b",
                "rtf": 1.15,
                "audio_duration_s": 28.0,
                "sample_rate_hz": 24000,
            },
        )


class _StubWanTool:
    def execute(self, inputs):
        Path(inputs["output_path"]).write_bytes(b"\x00" * 4096)
        return SimpleNamespace(
            success=True,
            error=None,
            data={
                "provider": "stub-wan22",
                "model": "wan22-mlx",
                "width": inputs.get("width"),
                "height": inputs.get("height"),
                "num_frames": inputs.get("num_frames"),
                "steps": inputs.get("steps"),
                "seed": inputs.get("seed"),
            },
        )


class _StubRegistry:
    def __init__(self):
        self._tools = {
            "vibevoice_tts": _StubVibeVoiceTool(),
            "wan22_mlx_video": _StubWanTool(),
        }

    def get(self, name):
        return self._tools.get(name)


class _StubStillsStage(FluxStillsStage):
    def __init__(self):
        super().__init__()

    def is_available(self):
        return True

    def run(self, prompts, output_dir, brand_negative_prompt=""):
        stills = []
        for i, prompt in enumerate(prompts):
            out = Path(output_dir) / f"still_{i}.png"
            out.write_bytes(b"\x89PNG" + b"\x00" * 100)
            stills.append(
                StillResult(
                    index=i,
                    prompt=prompt,
                    status="success",
                    output_path=str(out),
                    duration_s=0.1,
                )
            )
        return StillsResult(
            status="success",
            model="stub-flux",
            stills=stills,
            total_duration_s=0.2,
        )


class _StubThumbnailQA(ThumbnailQAStage):
    def run(
        self,
        video_path,
        output_dir,
        brand_display_name,
        brand_negative_prompt,
        frame_time_seconds=0.5,
    ):
        thumb = Path(output_dir) / "qa_thumbnail.png"
        thumb.write_bytes(b"\x89PNG" + b"\x00" * 50)
        return ThumbnailQAResult(
            status="success",
            thumbnail_path=str(thumb),
            qa_text="STATUS: OK\nISSUES: none\nCONFIDENCE: 0.93",
            issues=[],
            confidence=0.93,
            duration_s=0.5,
            model="ui-tars-stub",
        )


def _fake_ffmpeg_run(cmd, **kwargs):
    """Stand-in for subprocess.run when the real ffmpeg would fail on fake bytes.

    The ensemble's ``_run_mux`` calls ffmpeg with ``-i video -i audio ... output``.
    The output path is the last positional argument in the command. We simply
    touch that file to simulate a successful mux.
    """
    # ffmpeg command ends with the output path
    output_path = Path(cmd[-1])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(b"\x00" * 2048)
    return SimpleNamespace(returncode=0, stdout="", stderr="")


class TestRunBriefIntegration:
    def _build(self, tmp_path, *, enable_remotion=False, num_stills=2, enable_qa=True):
        script_gen = MarketingScriptGenerator(
            client=_StubAsyncAnthropic(_valid_script_payload()),
            model="claude-haiku-4-5-20251001",
        )
        ensemble = SovereignMarketingEnsemble(
            output_root=tmp_path,
            registry_loader=lambda: _StubRegistry(),
            script_generator=script_gen,
            stills_stage=_StubStillsStage(),
            thumbnail_qa_stage=_StubThumbnailQA(),
        )
        brief = CampaignBrief(
            tenant="atx_mats",
            campaign_id="brief-test",
            subject="gym flooring launch",
            audience="commercial gym owners",
            objective=CampaignObjective.LAUNCH,
            key_message="Outlasts the warranty",
            call_to_action="Request a sample",
            num_stills=num_stills,
            enable_remotion=enable_remotion,
            enable_thumbnail_qa=enable_qa,
            require_publish_approval=True,
        )
        return ensemble, brief

    def test_happy_path_all_stages(self, tmp_path):
        ensemble, brief = self._build(tmp_path)
        with patch("subprocess.run", side_effect=_fake_ffmpeg_run):
            result = ensemble.run_brief(brief)
        stage_names = [s.stage for s in result.stages]
        # Expected sequence (remotion disabled, so only ffmpeg mux)
        # script_gen -> narration -> video -> stills -> mux -> thumbnail_qa -> publish_gate
        assert "script_gen" in stage_names
        assert "narration" in stage_names
        assert "video" in stage_names
        assert "stills" in stage_names
        assert "mux" in stage_names
        assert "thumbnail_qa" in stage_names
        assert "publish_gate" in stage_names
        # Artifacts
        assert "narration" in result.artifacts
        assert "video" in result.artifacts
        assert "still_0" in result.artifacts
        assert "still_1" in result.artifacts
        assert "final" in result.artifacts
        # script.json was persisted
        assert (Path(result.output_dir) / "script.json").exists()
        # publish_request.json was written by the gate
        assert (Path(result.output_dir) / "publish_request.json").exists()
        # The script-gen stage succeeded
        script_stage = next(s for s in result.stages if s.stage == "script_gen")
        assert script_stage.status == "success"
        assert script_stage.data["still_prompt_count"] == 2
        assert script_stage.data["caption_count"] == 3

    def test_script_gen_failure_short_circuits(self, tmp_path):
        ensemble, brief = self._build(tmp_path)
        ensemble._script_generator = MarketingScriptGenerator(
            client=_StubAsyncAnthropic("", raise_exc=RuntimeError("429"))
        )
        result = ensemble.run_brief(brief)
        assert result.status == "error"
        stage_names = [s.stage for s in result.stages]
        assert stage_names == ["script_gen"]  # no downstream stages ran

    def test_thumbnail_qa_disabled_skips(self, tmp_path):
        ensemble, brief = self._build(tmp_path, enable_qa=False)
        with patch("subprocess.run", side_effect=_fake_ffmpeg_run):
            result = ensemble.run_brief(brief)
        stage_names = [s.stage for s in result.stages]
        assert "thumbnail_qa" not in stage_names

    def test_publish_gate_not_required_skipped(self, tmp_path):
        ensemble, brief = self._build(tmp_path)
        brief_no_pub = CampaignBrief(
            tenant=brief.tenant,
            campaign_id="no-pub",
            subject=brief.subject,
            audience=brief.audience,
            objective=brief.objective,
            key_message=brief.key_message,
            call_to_action=brief.call_to_action,
            num_stills=0,
            enable_thumbnail_qa=False,
            require_publish_approval=False,
        )
        with patch("subprocess.run", side_effect=_fake_ffmpeg_run):
            result = ensemble.run_brief(brief_no_pub)
        stage_names = [s.stage for s in result.stages]
        assert "publish_gate" not in stage_names


# ---------- MarketingAgent new intent ----------


class TestMarketingAgentBriefIntent:
    def test_produce_campaign_from_brief(self, tmp_path):
        script_gen = MarketingScriptGenerator(
            client=_StubAsyncAnthropic(_valid_script_payload()),
        )
        ensemble = SovereignMarketingEnsemble(
            output_root=tmp_path,
            registry_loader=lambda: _StubRegistry(),
            script_generator=script_gen,
            stills_stage=_StubStillsStage(),
            thumbnail_qa_stage=_StubThumbnailQA(),
        )
        agent = MarketingAgent(ensemble=ensemble)

        brief_data = {
            "tenant": "atx_mats",
            "campaign_id": "agent-brief-test",
            "subject": "gym flooring launch",
            "audience": "commercial gym owners",
            "objective": "launch",
            "key_message": "Outlasts the warranty",
            "call_to_action": "Request a sample",
            "platforms": ["linkedin"],
            "num_stills": 1,
            "enable_thumbnail_qa": False,
            "require_publish_approval": False,
        }
        req = SwarmAgentRequest(
            task="produce brief",
            parameters={
                "intent": "produce_campaign_from_brief",
                "brief": brief_data,
            },
        )
        with patch("subprocess.run", side_effect=_fake_ffmpeg_run):
            resp = asyncio.run(agent.execute(req))
        assert resp.status == "success"
        assert resp.data["campaign_id"] == "agent-brief-test"
        assert "narration" in resp.data["artifacts"]
        assert "video" in resp.data["artifacts"]

    def test_produce_campaign_from_brief_missing(self, tmp_path):
        ensemble = SovereignMarketingEnsemble(
            output_root=tmp_path,
            registry_loader=lambda: _StubRegistry(),
        )
        agent = MarketingAgent(ensemble=ensemble)
        req = SwarmAgentRequest(
            task="x", parameters={"intent": "produce_campaign_from_brief"}
        )
        resp = asyncio.run(agent.execute(req))
        assert resp.status == "error"
        assert "brief" in (resp.error or "")
