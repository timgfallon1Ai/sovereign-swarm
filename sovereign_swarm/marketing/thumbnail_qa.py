"""UI-TARS thumbnail QA stage.

After the motion video finishes rendering, this stage:
  1. Extracts a representative mid-frame via ffmpeg
  2. Asks UI-TARS (via sovereign_swarm.web_agent.UITarsBackend) to
     verify there are no artifacts — visible watermarks, garbled
     text, placeholder graphics, cartoon style if not wanted, etc.
  3. Returns a structured result with a confidence score, the
     thumbnail path, and any flagged issues.

The QA prompts are tenant-aware: each tenant's negative_prompt is
fed into the QA question so UI-TARS knows what to look for.

UI-TARS is loaded lazily on first use. If mlx-vlm isn't available in
the current venv (sovereign-swarm's venv doesn't ship it), the stage
returns ``status="skipped"`` with a clear install hint. Zero cost
when enabled — local MLX inference.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


QA_PROMPT_TEMPLATE = (
    "Review this frame extracted from a marketing video for {brand}. "
    "Check for the following issues: {negative_prompt}. "
    "Also flag any visible watermarks, placeholder text, garbled typography, "
    "duplicate subjects, or off-brand elements. "
    "Respond in this exact format:\n"
    "STATUS: OK or FLAGGED\n"
    "ISSUES: comma-separated list of specific problems, or 'none'\n"
    "CONFIDENCE: 0.0-1.0 confidence that the frame is on-brand and artifact-free"
)


@dataclass
class ThumbnailQAResult:
    status: str  # "success" | "flagged" | "error" | "skipped"
    thumbnail_path: Optional[str] = None
    qa_text: Optional[str] = None
    issues: list[str] = field(default_factory=list)
    confidence: Optional[float] = None
    duration_s: Optional[float] = None
    model: Optional[str] = None
    error: Optional[str] = None


class ThumbnailQAStage:
    """Extract a representative frame from a video and run it through UI-TARS."""

    def __init__(
        self,
        backend: Any = None,
        ffmpeg_binary: Optional[str] = None,
    ) -> None:
        self._backend = backend
        self._ffmpeg = ffmpeg_binary or shutil.which("ffmpeg") or "ffmpeg"

    def is_available(self) -> bool:
        if shutil.which(self._ffmpeg) is None:
            return False
        if self._backend is not None:
            return True
        # Lazy-check mlx-vlm availability without importing it
        try:
            import importlib.util

            return importlib.util.find_spec("mlx_vlm") is not None
        except Exception:  # noqa: BLE001
            return False

    def run(
        self,
        video_path: Path,
        output_dir: Path,
        brand_display_name: str,
        brand_negative_prompt: str,
        frame_time_seconds: float = 0.5,
    ) -> ThumbnailQAResult:
        """Extract a frame and run UI-TARS QA against it."""
        t0 = time.time()
        if not video_path.exists():
            return ThumbnailQAResult(
                status="error",
                duration_s=round(time.time() - t0, 2),
                error=f"video_path does not exist: {video_path}",
            )
        if shutil.which(self._ffmpeg) is None:
            return ThumbnailQAResult(
                status="skipped",
                duration_s=round(time.time() - t0, 2),
                error="ffmpeg not found on PATH",
            )

        thumbnail_path = output_dir / "qa_thumbnail.png"
        thumbnail_path.parent.mkdir(parents=True, exist_ok=True)
        extract_err = self._extract_frame(
            video_path, thumbnail_path, frame_time_seconds
        )
        if extract_err is not None:
            return ThumbnailQAResult(
                status="error",
                duration_s=round(time.time() - t0, 2),
                error=extract_err,
            )

        backend = self._ensure_backend()
        if backend is None:
            return ThumbnailQAResult(
                status="skipped",
                thumbnail_path=str(thumbnail_path),
                duration_s=round(time.time() - t0, 2),
                error=(
                    "UI-TARS backend unavailable. Install mlx-vlm and the "
                    "UI-TARS-1.5-7B-4bit MLX model, or construct "
                    "ThumbnailQAStage with a pre-built backend."
                ),
            )

        prompt = QA_PROMPT_TEMPLATE.format(
            brand=brand_display_name,
            negative_prompt=brand_negative_prompt,
        )
        try:
            resp = backend.answer(str(thumbnail_path), prompt, max_tokens=256)
        except Exception as exc:  # noqa: BLE001
            return ThumbnailQAResult(
                status="error",
                thumbnail_path=str(thumbnail_path),
                duration_s=round(time.time() - t0, 2),
                error=f"{type(exc).__name__}: {exc}",
            )

        text = (getattr(resp, "text", "") or "").strip()
        parsed = _parse_qa_response(text)
        return ThumbnailQAResult(
            status=parsed["status"],
            thumbnail_path=str(thumbnail_path),
            qa_text=text,
            issues=parsed["issues"],
            confidence=parsed["confidence"],
            duration_s=round(time.time() - t0, 2),
            model=getattr(resp, "model", None),
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _ensure_backend(self) -> Any:
        if self._backend is not None:
            return self._backend
        try:
            from sovereign_swarm.web_agent.backend import UITarsBackend

            self._backend = UITarsBackend()
        except Exception as exc:  # noqa: BLE001
            logger.debug("thumbnail_qa: backend init failed: %s", exc)
            return None
        return self._backend

    def _extract_frame(
        self,
        video_path: Path,
        thumbnail_path: Path,
        frame_time_seconds: float,
    ) -> Optional[str]:
        """Return an error string or None on success."""
        cmd = [
            self._ffmpeg,
            "-y",
            "-ss",
            str(frame_time_seconds),
            "-i",
            str(video_path),
            "-frames:v",
            "1",
            "-q:v",
            "2",
            str(thumbnail_path),
        ]
        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=True, timeout=60
            )
        except Exception as exc:  # noqa: BLE001
            return f"ffmpeg frame extraction failed: {type(exc).__name__}: {exc}"
        if proc.returncode != 0:
            return (
                f"ffmpeg exit {proc.returncode} during frame extraction: "
                f"{proc.stderr[-300:]}"
            )
        if not thumbnail_path.exists():
            return f"ffmpeg produced no output at {thumbnail_path}"
        return None


# ---------------------------------------------------------------------------
# QA response parsing
# ---------------------------------------------------------------------------


def _parse_qa_response(text: str) -> dict[str, Any]:
    """Parse the STATUS/ISSUES/CONFIDENCE format into a dict.

    Accepts loose casing and whitespace. Falls back to conservative
    defaults (status='flagged', confidence=0.5) if the model ignored
    the format.
    """
    out: dict[str, Any] = {
        "status": "flagged",
        "issues": [],
        "confidence": 0.5,
    }
    if not text:
        return out

    lower = text.lower()
    # Status
    if "status:" in lower:
        status_line = lower.split("status:", 1)[1].splitlines()[0].strip()
        if status_line.startswith("ok"):
            out["status"] = "success"
        elif status_line.startswith("flag"):
            out["status"] = "flagged"
    elif "all clear" in lower or "looks good" in lower:
        out["status"] = "success"

    # Issues
    if "issues:" in lower:
        issues_line = lower.split("issues:", 1)[1].splitlines()[0].strip()
        if issues_line and issues_line != "none":
            out["issues"] = [
                i.strip() for i in issues_line.split(",") if i.strip()
            ]

    # Confidence
    if "confidence:" in lower:
        conf_line = lower.split("confidence:", 1)[1].splitlines()[0].strip()
        try:
            out["confidence"] = max(0.0, min(1.0, float(conf_line)))
        except ValueError:
            pass

    return out
