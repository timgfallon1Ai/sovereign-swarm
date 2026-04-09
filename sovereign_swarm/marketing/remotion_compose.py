"""Remotion composition wrapper for the marketing ensemble.

Replaces the Phase 1 ffmpeg-loop mux with a Remotion-based
compositor that can layer:
  - the Wan 2.2 motion video as the main video track
  - the VibeVoice narration as the audio track
  - optional caption overlays (word-level or beat-level)
  - optional tenant-branded lower thirds / section titles
  - optional FLUX still-image cutaways

Drives the existing OpenMontage Remotion composer at
``~/Documents/GitHub/OpenMontage/remotion-composer/``. The composer
already ships several compositions — we target the ``Explainer``
composition (1920x1080, 30fps, variable duration) because its
``defaultProps`` accept the exact shape we produce here: cuts[],
overlays[], captions[], audio{}.

The wrapper falls back to ffmpeg-loop mux cleanly if:
  - the composer directory is missing
  - Node / npx is not installed
  - node_modules is not installed (missing Remotion CLI)
  - the render itself fails

This keeps the ensemble robust: Remotion is an enhancement, not a
hard dependency.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


DEFAULT_COMPOSER_DIR = "~/Documents/GitHub/OpenMontage/remotion-composer"
DEFAULT_COMPOSITION_ID = "Explainer"
DEFAULT_ENTRY = "src/index.tsx"


@dataclass
class RemotionResult:
    status: str  # "success" | "skipped" | "error"
    output_path: Optional[str] = None
    composition_id: Optional[str] = None
    duration_s: Optional[float] = None
    error: Optional[str] = None
    stderr_tail: Optional[str] = None


class RemotionComposerStage:
    """Wrapper around `npx remotion render` for campaign composition."""

    def __init__(
        self,
        composer_dir: Optional[str] = None,
        composition_id: str = DEFAULT_COMPOSITION_ID,
        entry_file: str = DEFAULT_ENTRY,
        npx_binary: Optional[str] = None,
    ) -> None:
        self.composer_dir = Path(
            os.path.expanduser(composer_dir or DEFAULT_COMPOSER_DIR)
        )
        self.composition_id = composition_id
        self.entry_file = entry_file
        self.npx = npx_binary or shutil.which("npx") or "npx"

    def is_available(self) -> bool:
        if not self.composer_dir.exists():
            return False
        if not (self.composer_dir / "node_modules").exists():
            return False
        if shutil.which(self.npx) is None:
            return False
        return True

    def run(
        self,
        video_path: Path,
        audio_path: Path,
        output_path: Path,
        brand: Any,
        captions: Optional[list[str]] = None,
        still_paths: Optional[list[str]] = None,
        title_text: Optional[str] = None,
    ) -> RemotionResult:
        """Render a final mp4 via Remotion with video + audio + optional overlays.

        On any failure returns ``status="skipped"`` or ``status="error"``
        so the caller can fall back to ffmpeg-loop mux.
        """
        t0 = time.time()
        if not self.is_available():
            return RemotionResult(
                status="skipped",
                composition_id=self.composition_id,
                duration_s=round(time.time() - t0, 2),
                error=(
                    f"Remotion composer not ready at {self.composer_dir} "
                    "(install with: cd remotion-composer && npm install)"
                ),
            )
        if not video_path.exists():
            return RemotionResult(
                status="error",
                duration_s=round(time.time() - t0, 2),
                error=f"video_path missing: {video_path}",
            )
        if not audio_path.exists():
            return RemotionResult(
                status="error",
                duration_s=round(time.time() - t0, 2),
                error=f"audio_path missing: {audio_path}",
            )

        output_path.parent.mkdir(parents=True, exist_ok=True)

        props = self._build_props(
            video_path=video_path,
            audio_path=audio_path,
            brand=brand,
            captions=captions or [],
            still_paths=still_paths or [],
            title_text=title_text,
        )

        props_path = output_path.parent / "remotion_props.json"
        props_path.write_text(json.dumps(props, indent=2))

        cmd = [
            self.npx,
            "--yes",
            "remotion",
            "render",
            self.entry_file,
            self.composition_id,
            str(output_path),
            "--props",
            str(props_path),
        ]

        # Scrub VIRTUAL_ENV so Node doesn't pick up a Python venv's PATH
        env = os.environ.copy()
        for var in ("VIRTUAL_ENV", "PYTHONHOME", "PYTHONPATH"):
            env.pop(var, None)

        try:
            proc = subprocess.run(
                cmd,
                cwd=str(self.composer_dir),
                capture_output=True,
                text=True,
                timeout=1800,  # 30 min hard cap — Remotion renders are usually fast
                env=env,
            )
        except Exception as exc:  # noqa: BLE001
            return RemotionResult(
                status="error",
                composition_id=self.composition_id,
                duration_s=round(time.time() - t0, 2),
                error=f"{type(exc).__name__}: {exc}",
            )

        if proc.returncode != 0:
            return RemotionResult(
                status="error",
                composition_id=self.composition_id,
                duration_s=round(time.time() - t0, 2),
                error=f"remotion render exit {proc.returncode}",
                stderr_tail=proc.stderr[-800:],
            )
        if not output_path.exists():
            return RemotionResult(
                status="error",
                composition_id=self.composition_id,
                duration_s=round(time.time() - t0, 2),
                error="remotion succeeded but no output file written",
                stderr_tail=proc.stderr[-400:],
            )

        return RemotionResult(
            status="success",
            output_path=str(output_path),
            composition_id=self.composition_id,
            duration_s=round(time.time() - t0, 2),
        )

    # ------------------------------------------------------------------
    # Props construction
    # ------------------------------------------------------------------

    def _build_props(
        self,
        video_path: Path,
        audio_path: Path,
        brand: Any,
        captions: list[str],
        still_paths: list[str],
        title_text: Optional[str],
    ) -> dict[str, Any]:
        """Build the defaultProps payload the Explainer composition expects.

        The Explainer composition in Root.tsx declares:
            cuts: [],
            overlays: [],
            captions: [],
            audio: {},

        We populate each of those with the minimum shape the Explainer
        React component knows how to render. The exact schema is
        deliberately forgiving — the composition gracefully ignores
        unknown fields, so we provide rich data and let the renderer
        pick what it needs.
        """
        palette = list(getattr(brand, "palette", ())) or ["#111111", "#ffffff"]
        display_name = getattr(brand, "display_name", "")
        tagline = getattr(brand, "tagline", "")

        cuts: list[dict[str, Any]] = [
            {
                "type": "video",
                "src": str(video_path),
                "loop": True,
                "fit": "cover",
            }
        ]
        for i, still in enumerate(still_paths):
            cuts.append(
                {
                    "type": "image",
                    "src": still,
                    "fit": "cover",
                    "beat_index": i,
                }
            )

        overlays: list[dict[str, Any]] = []
        if title_text or display_name:
            overlays.append(
                {
                    "kind": "hero_title",
                    "text": title_text or display_name,
                    "subtitle": tagline,
                    "palette": palette,
                }
            )

        caption_beats: list[dict[str, Any]] = [
            {"text": c, "index": i} for i, c in enumerate(captions)
        ]

        return {
            "cuts": cuts,
            "overlays": overlays,
            "captions": caption_beats,
            "audio": {"src": str(audio_path)},
            "palette": palette,
            "brand_name": display_name,
        }
