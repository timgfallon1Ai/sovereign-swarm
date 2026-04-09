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

import json
import logging
import shutil
import subprocess
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Optional

from sovereign_swarm.marketing.brand import TenantBrand, get_brand

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
    """Stateless pipeline driver for per-tenant marketing asset production."""

    def __init__(
        self,
        output_root: str | Path = "~/Documents/sovereign_marketing_runs",
        registry_loader: Optional[Callable[[], Any]] = None,
        ffmpeg_binary: Optional[str] = None,
    ) -> None:
        self.output_root = Path(str(output_root)).expanduser()
        self._registry_loader = registry_loader or _default_registry_loader
        self._ffmpeg = ffmpeg_binary or shutil.which("ffmpeg")

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
