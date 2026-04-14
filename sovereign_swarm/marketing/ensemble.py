"""SovereignMarketingEnsemble — shared cross-tenant marketing production.

Stitches together Claude (script/research), VibeVoice (narration),
Wan 2.2 MLX (motion video), and ffmpeg (muxing) into a single
reproducible pipeline that can be invoked by any tenant (ATX Mats,
GBB, GLI) with a handful of parameters.

Phase 1 scope (this module): campaign planning + asset generation.
No execution / publishing. The output is a ``MarketingCampaignResult``
with file paths, metadata, and a structured log of every stage.

Design notes
------------
- The ensemble does NOT orchestrate via OpenMontage's agent loop.
  It calls the OpenMontage tool registry directly for narration +
  video generation, which is simpler to drive from inside the swarm
  runtime and doesn't require the full OpenMontage pipeline YAML
  machinery.
- OpenMontage is imported lazily via a helper so tests and swarm
  consumers can substitute a stub or use an alternate provider.
- The ensemble is deliberately dumb about scripting — it expects the
  caller to supply the actual narration text (or a callback that
  produces it). This keeps the LLM choice out of the ensemble and
  defers scripting to ContentAgent, a direct Claude call, or a
  hand-written script.
- All outputs land under ``<output_dir>/<tenant>/<campaign_id>/``
  with a manifest.json capturing the full run.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import json
import logging
import shutil
import subprocess
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable, Mapping, Optional, TypeVar

_T = TypeVar("_T")


def _run_coroutine_sync(coro: Awaitable[_T]) -> _T:
    """Run an async coroutine from synchronous code, robust to an already-running loop.

    ``asyncio.run()`` cannot be called when a loop is already running in the
    current thread (which happens under some pytest configurations and
    nested-loop scenarios). This helper tries the fast path first and falls
    back to running the coroutine in a dedicated worker thread with its own
    fresh event loop.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        # No running loop in this thread — safe to use asyncio.run directly.
        return asyncio.run(coro)

    # There's already a loop running here. Execute in a worker thread.
    result_box: dict[str, Any] = {}

    def _worker() -> None:
        loop = asyncio.new_event_loop()
        try:
            result_box["value"] = loop.run_until_complete(coro)
        except BaseException as exc:  # noqa: BLE001
            result_box["error"] = exc
        finally:
            loop.close()

    thread = threading.Thread(target=_worker, name="marketing-ensemble-async", daemon=True)
    thread.start()
    thread.join()
    if "error" in result_box:
        raise result_box["error"]
    return result_box["value"]

from sovereign_swarm.marketing.brand import TenantBrand, get_brand
from sovereign_swarm.marketing.brief import CampaignBrief
from sovereign_swarm.marketing.canva_stage import CanvaDesignStage
from sovereign_swarm.marketing.publish_gate import PublishGate, PublishRequest
from sovereign_swarm.marketing.remotion_compose import RemotionComposerStage
from sovereign_swarm.marketing.script_gen import (
    MarketingScriptGenerator,
    ScriptResult,
)
from sovereign_swarm.marketing.stills import FluxStillsStage, StillsResult
from sovereign_swarm.marketing.thumbnail_qa import (
    ThumbnailQAResult,
    ThumbnailQAStage,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Request / result dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MarketingCampaignRequest:
    """Everything the ensemble needs to produce one campaign asset."""

    tenant: str  # e.g. "atx_mats", "gbb", "gli"
    campaign_id: str  # stable identifier used in paths + manifest
    narration_text: str  # the line the VibeVoice speaker will read
    video_prompt: str  # the prompt handed to Wan 2.2 for motion video
    # Optional overrides — sensible tenant defaults otherwise
    duration_seconds: Optional[int] = None
    resolution: Optional[tuple[int, int]] = None
    num_frames: Optional[int] = None
    steps: Optional[int] = None
    seed: int = 7
    extra_negative_prompt: str = ""  # appended to tenant brand negative prompt
    notes: str = ""


@dataclass
class StageLog:
    stage: str
    status: str  # "success" | "skipped" | "error"
    duration_s: Optional[float] = None
    output: Optional[str] = None
    data: dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None


@dataclass
class MarketingCampaignResult:
    tenant: str
    campaign_id: str
    timestamp: str
    output_dir: str
    brand: dict[str, Any]
    stages: list[StageLog] = field(default_factory=list)
    artifacts: dict[str, str] = field(default_factory=dict)
    status: str = "success"  # "success" | "partial" | "error"
    total_cost_usd: float = 0.0
    total_duration_s: float = 0.0
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# Ensemble
# ---------------------------------------------------------------------------


class SovereignMarketingEnsemble:
    """Stateless pipeline driver for per-tenant marketing asset production.

    Exposes two run modes:

    * ``run(request)`` — Phase 1 mode. Takes a ``MarketingCampaignRequest``
      with pre-written narration text + video prompt and drives the
      narration → video → mux pipeline.
    * ``run_brief(brief)`` — Phase 2 mode. Takes a structured
      ``CampaignBrief``, uses Claude to generate the narration + video
      prompt + still prompts + captions, then drives the full pipeline
      including optional stills, Remotion composition, thumbnail QA,
      and a publish-gate handshake.

    Both modes share the same output layout and manifest format.
    """

    def __init__(
        self,
        output_root: str | Path = "~/Documents/sovereign_marketing_runs",
        registry_loader: Optional[Callable[[], Any]] = None,
        ffmpeg_binary: Optional[str] = None,
        script_generator: Optional[MarketingScriptGenerator] = None,
        stills_stage: Optional[FluxStillsStage] = None,
        thumbnail_qa_stage: Optional[ThumbnailQAStage] = None,
        remotion_stage: Optional[RemotionComposerStage] = None,
        publish_gate: Optional[PublishGate] = None,
        canva_stage: Optional[CanvaDesignStage] = None,
    ) -> None:
        self.output_root = Path(str(output_root)).expanduser()
        self._registry_loader = registry_loader or _default_registry_loader
        self._ffmpeg = ffmpeg_binary or shutil.which("ffmpeg")
        self._script_generator = script_generator
        self._stills_stage = stills_stage
        self._thumbnail_qa_stage = thumbnail_qa_stage
        self._remotion_stage = remotion_stage
        self._publish_gate = publish_gate
        self._canva_stage = canva_stage

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self, request: MarketingCampaignRequest) -> MarketingCampaignResult:
        """Execute a campaign synchronously. Returns the full result manifest."""
        brand = get_brand(request.tenant)
        output_dir = self._prepare_output_dir(brand, request)
        t0 = time.time()
        result = MarketingCampaignResult(
            tenant=brand.key,
            campaign_id=request.campaign_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            output_dir=str(output_dir),
            brand=asdict(brand),
        )

        # Stage 1: narration via VibeVoice (through OpenMontage registry)
        narration_path = output_dir / "narration.wav"
        stage = self._run_narration(brand, request, narration_path)
        result.stages.append(stage)
        if stage.status == "success":
            result.artifacts["narration"] = str(narration_path)

        # Stage 2: motion video via Wan 2.2 MLX (through OpenMontage registry)
        video_path = output_dir / "motion.mp4"
        stage = self._run_video(brand, request, video_path)
        result.stages.append(stage)
        if stage.status == "success":
            result.artifacts["video"] = str(video_path)

        # Stage 3: mux narration + video into final deliverable
        final_path = output_dir / "final.mp4"
        stage = self._run_mux(narration_path, video_path, final_path)
        result.stages.append(stage)
        if stage.status == "success":
            result.artifacts["final"] = str(final_path)

        result.total_duration_s = round(time.time() - t0, 2)
        result.status = self._summarize_status(result.stages)
        self._write_manifest(output_dir, result)
        return result

    def run_brief(self, brief: CampaignBrief) -> MarketingCampaignResult:
        """Phase 2 entry point — full pipeline driven by a structured brief.

        Pipeline:
          1. Claude script generation  -> narration_text + video_prompt
                                          + still_prompts + captions
          2. VibeVoice narration (Phase 1)
          3. Wan 2.2 MLX motion video (Phase 1)
          4. FLUX still images (if brief.num_stills > 0)
          5. Remotion composition (if brief.enable_remotion) or
             ffmpeg-loop mux fallback
          6. UI-TARS thumbnail QA (if brief.enable_thumbnail_qa)
          7. Publish-gate handshake (if brief.require_publish_approval)

        Any stage failure is captured in the stage log and the pipeline
        continues as far as it can. The final ``status`` is ``success``
        if every critical stage (narration, video, final) succeeded,
        ``partial`` if some artifacts were produced, ``error`` otherwise.
        """
        brand = get_brand(brief.tenant)
        # Build a synthetic request so _prepare_output_dir reuses existing layout
        synthetic = MarketingCampaignRequest(
            tenant=brief.tenant,
            campaign_id=brief.campaign_id,
            narration_text="",  # filled by script-gen stage below
            video_prompt="",
            duration_seconds=brief.duration_seconds,
            resolution=brief.resolution,
            notes=brief.notes,
        )
        output_dir = self._prepare_output_dir(brand, synthetic)
        t0 = time.time()
        result = MarketingCampaignResult(
            tenant=brand.key,
            campaign_id=brief.campaign_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            output_dir=str(output_dir),
            brand=asdict(brand),
        )

        # Stage 1: script generation (Claude)
        script_stage, script = self._run_script_gen(brief, brand)
        result.stages.append(script_stage)
        if script_stage.status != "success" or script is None:
            # No script -> cannot continue meaningfully. Finalize and return.
            result.total_duration_s = round(time.time() - t0, 2)
            result.status = "error"
            self._write_manifest(output_dir, result)
            return result

        # Persist the script package alongside the campaign for auditability
        (output_dir / "script.json").write_text(
            json.dumps(
                {
                    "narration_text": script.narration_text,
                    "video_prompt": script.video_prompt,
                    "still_prompts": script.still_prompts,
                    "captions": script.captions,
                    "rationale": script.rationale,
                    "warnings": script.warnings,
                    "model": script.model,
                },
                indent=2,
            )
        )

        # Stage 2: narration
        narration_path = output_dir / "narration.wav"
        narration_request = MarketingCampaignRequest(
            tenant=brief.tenant,
            campaign_id=brief.campaign_id,
            narration_text=script.narration_text or "",
            video_prompt=script.video_prompt or "",
        )
        stage = self._run_narration(brand, narration_request, narration_path)
        result.stages.append(stage)
        if stage.status == "success":
            result.artifacts["narration"] = str(narration_path)

        # Stage 3: motion video
        video_path = output_dir / "motion.mp4"
        video_request = MarketingCampaignRequest(
            tenant=brief.tenant,
            campaign_id=brief.campaign_id,
            narration_text=script.narration_text or "",
            video_prompt=script.video_prompt or "",
            resolution=brief.resolution,
            num_frames=synthetic.num_frames,
            steps=synthetic.steps,
            seed=synthetic.seed,
        )
        stage = self._run_video(brand, video_request, video_path)
        result.stages.append(stage)
        if stage.status == "success":
            result.artifacts["video"] = str(video_path)

        # Stage 4: still images (optional)
        if brief.num_stills > 0 and script.still_prompts:
            stage, stills_result = self._run_stills(
                brand,
                script.still_prompts[: brief.num_stills],
                output_dir,
            )
            result.stages.append(stage)
            if stills_result is not None:
                for i, s in enumerate(stills_result.stills):
                    if s.output_path:
                        result.artifacts[f"still_{i}"] = s.output_path

        # Stage 5: final composition — Remotion if requested, else ffmpeg mux
        final_path = output_dir / "final.mp4"
        if brief.enable_remotion:
            stage = self._run_remotion(
                video_path=video_path,
                audio_path=narration_path,
                output_path=final_path,
                brand=brand,
                captions=script.captions,
                still_paths=[
                    p for k, p in result.artifacts.items() if k.startswith("still_")
                ],
                title_text=None,
            )
            result.stages.append(stage)
            # Fall back to ffmpeg mux if Remotion was skipped / errored
            if stage.status != "success":
                mux_stage = self._run_mux(narration_path, video_path, final_path)
                result.stages.append(mux_stage)
        else:
            stage = self._run_mux(narration_path, video_path, final_path)
            result.stages.append(stage)
        if final_path.exists():
            result.artifacts["final"] = str(final_path)

        # Stage 6: thumbnail QA (optional)
        if brief.enable_thumbnail_qa and final_path.exists():
            stage = self._run_thumbnail_qa(
                video_path=final_path,
                output_dir=output_dir,
                brand=brand,
            )
            result.stages.append(stage)
            qa_thumb = output_dir / "qa_thumbnail.png"
            if qa_thumb.exists():
                result.artifacts["qa_thumbnail"] = str(qa_thumb)

        # Stage 7: Canva design generation (optional)
        if self._canva_stage and script:
            stage = self._run_canva_design(
                brand=brand,
                campaign_id=brief.campaign_id,
                headline=script.narration_text[:80] if script.narration_text else brief.campaign_id,
                body_text=script.rationale or "",
                platforms=[p.value for p in brief.platforms] if brief.platforms else ["instagram"],
                output_dir=output_dir,
            )
            result.stages.append(stage)
            canva_req_path = output_dir / "canva_request.json"
            if canva_req_path.exists():
                result.artifacts["canva_request"] = str(canva_req_path)

        # Stage 8: publish-gate handshake (optional)
        if brief.require_publish_approval and final_path.exists():
            stage = self._run_publish_gate(
                output_dir=output_dir,
                brief=brief,
                result_artifacts=dict(result.artifacts),
            )
            result.stages.append(stage)

        result.total_duration_s = round(time.time() - t0, 2)
        result.status = self._summarize_status(result.stages)
        self._write_manifest(output_dir, result)
        return result

    # ------------------------------------------------------------------
    # Stage implementations
    # ------------------------------------------------------------------

    def _run_narration(
        self,
        brand: TenantBrand,
        request: MarketingCampaignRequest,
        output_path: Path,
    ) -> StageLog:
        t0 = time.time()
        try:
            registry = self._registry_loader()
            tool = registry.get("vibevoice_tts")
            if tool is None:
                return StageLog(
                    stage="narration",
                    status="error",
                    duration_s=round(time.time() - t0, 2),
                    error="vibevoice_tts not registered — install and smoke-test it first",
                )
            resp = tool.execute(
                {
                    "text": request.narration_text,
                    "speaker_name": brand.voice_name,
                    "output_path": str(output_path),
                }
            )
        except Exception as exc:  # noqa: BLE001
            return StageLog(
                stage="narration",
                status="error",
                duration_s=round(time.time() - t0, 2),
                error=f"{type(exc).__name__}: {exc}",
            )
        if not getattr(resp, "success", False):
            return StageLog(
                stage="narration",
                status="error",
                duration_s=round(time.time() - t0, 2),
                error=getattr(resp, "error", "unknown"),
            )
        return StageLog(
            stage="narration",
            status="success",
            duration_s=round(time.time() - t0, 2),
            output=str(output_path),
            data={
                "provider": resp.data.get("provider"),
                "model": resp.data.get("model"),
                "rtf": resp.data.get("rtf"),
                "audio_duration_s": resp.data.get("audio_duration_s"),
                "sample_rate_hz": resp.data.get("sample_rate_hz"),
            },
        )

    def _run_video(
        self,
        brand: TenantBrand,
        request: MarketingCampaignRequest,
        output_path: Path,
    ) -> StageLog:
        t0 = time.time()
        try:
            registry = self._registry_loader()
            tool = registry.get("wan22_mlx_video")
            if tool is None:
                return StageLog(
                    stage="video",
                    status="error",
                    duration_s=round(time.time() - t0, 2),
                    error="wan22_mlx_video not registered — install and smoke-test it first",
                )
            width, height = request.resolution or brand.default_resolution
            num_frames = request.num_frames or 97
            steps = request.steps or 30
            negative = brand.negative_prompt
            if request.extra_negative_prompt:
                negative = f"{negative}, {request.extra_negative_prompt}"
            resp = tool.execute(
                {
                    "prompt": request.video_prompt,
                    "negative_prompt": negative,
                    "width": width,
                    "height": height,
                    "num_frames": num_frames,
                    "steps": steps,
                    "guide_scale": 5.0,
                    "shift": 5.0,
                    "scheduler": "unipc",
                    "seed": request.seed,
                    "output_path": str(output_path),
                }
            )
        except Exception as exc:  # noqa: BLE001
            return StageLog(
                stage="video",
                status="error",
                duration_s=round(time.time() - t0, 2),
                error=f"{type(exc).__name__}: {exc}",
            )
        if not getattr(resp, "success", False):
            return StageLog(
                stage="video",
                status="error",
                duration_s=round(time.time() - t0, 2),
                error=getattr(resp, "error", "unknown"),
            )
        return StageLog(
            stage="video",
            status="success",
            duration_s=round(time.time() - t0, 2),
            output=str(output_path),
            data={
                "provider": resp.data.get("provider"),
                "model": resp.data.get("model"),
                "width": resp.data.get("width"),
                "height": resp.data.get("height"),
                "num_frames": resp.data.get("num_frames"),
                "steps": resp.data.get("steps"),
                "seed": resp.data.get("seed"),
                "probe_duration": resp.data.get("probe_duration"),
                "probe_codec_name": resp.data.get("probe_codec_name"),
            },
        )

    def _run_mux(
        self,
        narration_path: Path,
        video_path: Path,
        output_path: Path,
    ) -> StageLog:
        t0 = time.time()
        if not self._ffmpeg:
            return StageLog(
                stage="mux",
                status="skipped",
                duration_s=round(time.time() - t0, 2),
                error="ffmpeg not found on PATH; narration + video produced but not muxed",
            )
        if not narration_path.exists() or not video_path.exists():
            return StageLog(
                stage="mux",
                status="skipped",
                duration_s=round(time.time() - t0, 2),
                error="prerequisite artifact missing (narration or video)",
            )
        cmd = [
            self._ffmpeg,
            "-y",
            "-stream_loop", "-1",
            "-i", str(video_path),
            "-i", str(narration_path),
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-c:a", "aac",
            "-shortest",
            "-movflags", "+faststart",
            str(output_path),
        ]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        except Exception as exc:  # noqa: BLE001
            return StageLog(
                stage="mux",
                status="error",
                duration_s=round(time.time() - t0, 2),
                error=f"{type(exc).__name__}: {exc}",
            )
        if proc.returncode != 0:
            return StageLog(
                stage="mux",
                status="error",
                duration_s=round(time.time() - t0, 2),
                error=f"ffmpeg exit {proc.returncode}: {proc.stderr[-600:]}",
            )
        return StageLog(
            stage="mux",
            status="success",
            duration_s=round(time.time() - t0, 2),
            output=str(output_path),
        )

    # ------------------------------------------------------------------
    # Phase 2 stage implementations
    # ------------------------------------------------------------------

    def _run_script_gen(
        self, brief: CampaignBrief, brand: TenantBrand
    ) -> tuple[StageLog, Optional[ScriptResult]]:
        t0 = time.time()
        gen = self._script_generator
        if gen is None:
            return (
                StageLog(
                    stage="script_gen",
                    status="error",
                    duration_s=round(time.time() - t0, 2),
                    error=(
                        "no script generator configured. Pass "
                        "script_generator=MarketingScriptGenerator(client=...) "
                        "to SovereignMarketingEnsemble()."
                    ),
                ),
                None,
            )
        try:
            script = _run_coroutine_sync(gen.generate(brief, brand))
        except Exception as exc:  # noqa: BLE001
            return (
                StageLog(
                    stage="script_gen",
                    status="error",
                    duration_s=round(time.time() - t0, 2),
                    error=f"{type(exc).__name__}: {exc}",
                ),
                None,
            )
        stage_status = "success" if script.success else "error"
        return (
            StageLog(
                stage="script_gen",
                status=stage_status,
                duration_s=round(time.time() - t0, 2),
                output=None,
                data={
                    "model": script.model,
                    "input_tokens": script.input_tokens,
                    "output_tokens": script.output_tokens,
                    "rationale": script.rationale,
                    "warnings": script.warnings,
                    "still_prompt_count": len(script.still_prompts),
                    "caption_count": len(script.captions),
                },
                error=script.error if not script.success else None,
            ),
            script,
        )

    def _run_stills(
        self,
        brand: TenantBrand,
        still_prompts: list[str],
        output_dir: Path,
    ) -> tuple[StageLog, Optional[StillsResult]]:
        t0 = time.time()
        stage_impl = self._stills_stage or FluxStillsStage(
            negative_prompt=brand.negative_prompt
        )
        try:
            result = stage_impl.run(
                prompts=still_prompts,
                output_dir=output_dir,
                brand_negative_prompt=brand.negative_prompt,
            )
        except Exception as exc:  # noqa: BLE001
            return (
                StageLog(
                    stage="stills",
                    status="error",
                    duration_s=round(time.time() - t0, 2),
                    error=f"{type(exc).__name__}: {exc}",
                ),
                None,
            )
        stage_status_map = {
            "success": "success",
            "partial": "success",
            "skipped": "skipped",
            "disabled": "skipped",
            "error": "error",
        }
        return (
            StageLog(
                stage="stills",
                status=stage_status_map.get(result.status, "error"),
                duration_s=round(time.time() - t0, 2),
                data={
                    "model": result.model,
                    "requested": len(still_prompts),
                    "successful": result.success_count,
                    "per_still": [
                        {
                            "index": s.index,
                            "status": s.status,
                            "output_path": s.output_path,
                            "error": s.error,
                        }
                        for s in result.stills
                    ],
                },
                error=result.error,
            ),
            result,
        )

    def _run_remotion(
        self,
        video_path: Path,
        audio_path: Path,
        output_path: Path,
        brand: TenantBrand,
        captions: list[str],
        still_paths: list[str],
        title_text: Optional[str],
    ) -> StageLog:
        t0 = time.time()
        stage_impl = self._remotion_stage or RemotionComposerStage()
        try:
            result = stage_impl.run(
                video_path=video_path,
                audio_path=audio_path,
                output_path=output_path,
                brand=brand,
                captions=captions,
                still_paths=still_paths,
                title_text=title_text,
            )
        except Exception as exc:  # noqa: BLE001
            return StageLog(
                stage="remotion",
                status="error",
                duration_s=round(time.time() - t0, 2),
                error=f"{type(exc).__name__}: {exc}",
            )
        return StageLog(
            stage="remotion",
            status=result.status,  # "success" | "skipped" | "error"
            duration_s=round(time.time() - t0, 2),
            output=result.output_path,
            data={
                "composition_id": result.composition_id,
                "stderr_tail": result.stderr_tail,
            },
            error=result.error,
        )

    def _run_thumbnail_qa(
        self,
        video_path: Path,
        output_dir: Path,
        brand: TenantBrand,
    ) -> StageLog:
        t0 = time.time()
        stage_impl = self._thumbnail_qa_stage or ThumbnailQAStage()
        try:
            result = stage_impl.run(
                video_path=video_path,
                output_dir=output_dir,
                brand_display_name=brand.display_name,
                brand_negative_prompt=brand.negative_prompt,
            )
        except Exception as exc:  # noqa: BLE001
            return StageLog(
                stage="thumbnail_qa",
                status="error",
                duration_s=round(time.time() - t0, 2),
                error=f"{type(exc).__name__}: {exc}",
            )
        status_map = {
            "success": "success",
            "flagged": "success",  # flagged is still a successful QA run
            "skipped": "skipped",
            "error": "error",
        }
        return StageLog(
            stage="thumbnail_qa",
            status=status_map.get(result.status, "error"),
            duration_s=round(time.time() - t0, 2),
            output=result.thumbnail_path,
            data={
                "qa_status": result.status,
                "issues": result.issues,
                "confidence": result.confidence,
                "model": result.model,
                "qa_text": result.qa_text,
            },
            error=result.error,
        )

    def _run_publish_gate(
        self,
        output_dir: Path,
        brief: CampaignBrief,
        result_artifacts: dict[str, str],
    ) -> StageLog:
        t0 = time.time()
        gate = self._publish_gate or PublishGate()
        try:
            req = gate.request_approval(
                output_dir=output_dir,
                tenant=brief.tenant,
                campaign_id=brief.campaign_id,
                artifacts=result_artifacts,
                platforms=[p.value for p in brief.platforms],
                owner=brief.owner,
                notes=brief.notes,
            )
            state = gate.check_approval(output_dir, req)
        except Exception as exc:  # noqa: BLE001
            return StageLog(
                stage="publish_gate",
                status="error",
                duration_s=round(time.time() - t0, 2),
                error=f"{type(exc).__name__}: {exc}",
            )
        return StageLog(
            stage="publish_gate",
            status="success",
            duration_s=round(time.time() - t0, 2),
            output=str(output_dir / PublishGate.REQUEST_FILENAME),
            data={
                "approval_state": state.state,
                "approval_token_length": len(req.approval_token),
                "platforms": list(req.platforms),
            },
        )

    def _run_canva_design(
        self,
        brand: TenantBrand,
        campaign_id: str,
        headline: str,
        body_text: str,
        platforms: list[str],
        output_dir: Path,
    ) -> StageLog:
        """Generate Canva design requests for each target platform."""
        t0 = time.time()
        stage = self._canva_stage
        if stage is None:
            return StageLog(
                stage="canva_design",
                status="skipped",
                duration_s=round(time.time() - t0, 2),
                error="no canva_stage configured",
            )
        try:
            # Generate for first platform (primary asset)
            platform = platforms[0] if platforms else "instagram"
            result = stage.run(
                brand=brand,
                campaign_id=campaign_id,
                headline=headline,
                body_text=body_text,
                platform=platform,
                output_dir=output_dir,
            )
            return StageLog(
                stage="canva_design",
                status="success" if result.status in ("created", "pending") else "error",
                duration_s=round(time.time() - t0, 2),
                output=result.edit_url,
                data={
                    "canva_status": result.status,
                    "design_id": result.design_id,
                    "platform": platform,
                },
                error=result.error,
            )
        except Exception as exc:
            return StageLog(
                stage="canva_design",
                status="error",
                duration_s=round(time.time() - t0, 2),
                error=f"{type(exc).__name__}: {exc}",
            )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _prepare_output_dir(
        self, brand: TenantBrand, request: MarketingCampaignRequest
    ) -> Path:
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M%S")
        dir_path = (
            self.output_root
            / brand.key
            / f"{stamp}_{request.campaign_id}_{uuid.uuid4().hex[:6]}"
        )
        dir_path.mkdir(parents=True, exist_ok=True)
        return dir_path

    def _write_manifest(self, output_dir: Path, result: MarketingCampaignResult) -> None:
        try:
            manifest_path = output_dir / "manifest.json"
            payload = asdict(result)
            manifest_path.write_text(json.dumps(payload, indent=2, default=str))
        except Exception:  # noqa: BLE001
            logger.exception("marketing_ensemble.manifest_write_failed")

    @staticmethod
    def _summarize_status(stages: list[StageLog]) -> str:
        if all(s.status == "success" for s in stages):
            return "success"
        if any(s.status == "success" for s in stages):
            return "partial"
        return "error"


# ---------------------------------------------------------------------------
# Default registry loader
# ---------------------------------------------------------------------------


def _default_registry_loader() -> Any:
    """Import OpenMontage's tool registry and ensure it's discovered.

    Separate helper so tests can substitute a stub by passing
    ``registry_loader=lambda: stub`` to the ensemble constructor.
    """
    try:
        import sys

        openmontage_root = Path("~/Documents/GitHub/OpenMontage").expanduser()
        if openmontage_root.exists() and str(openmontage_root) not in sys.path:
            sys.path.insert(0, str(openmontage_root))
        from tools.tool_registry import registry  # type: ignore  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(
            "Failed to import OpenMontage tool registry. Make sure OpenMontage "
            "is cloned at ~/Documents/GitHub/OpenMontage and its requirements "
            "are installed. Underlying error: " + str(exc)
        ) from exc
    registry.ensure_discovered()
    return registry
