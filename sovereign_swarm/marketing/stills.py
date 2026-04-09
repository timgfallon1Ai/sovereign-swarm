"""FLUX still-image generation stage for the marketing ensemble.

Wraps the `inference.sh` CLI (the `ai-image-generation` skill) as a
reusable stage that produces N still images from a list of prompts
plus a tenant-specific negative prompt. Each still is written to
the campaign output directory as ``still_<index>.png``.

The stage is intentionally thin:
  - It does NOT do prompt engineering beyond passing through what
    the script-generation stage already produced.
  - It does NOT retry on single-image failures; the caller gets a
    ``StillsResult`` with per-index status and can decide what to do.
  - It uses subprocess isolation so OpenMontage's / swarm's venv
    stays clean of infsh internals.

CLI invocation shape (from the ai-image-generation skill):
    infsh app run falai/flux-dev-lora --input '{"prompt": "..."}'

Output parsing: the CLI typically prints a JSON result with a URL or
a local file path. The wrapper supports either a direct
``output_path`` hint via the input payload OR post-hoc discovery via
stdout parsing. For tests / CI with no CLI installed, the stage
degrades to ``status="disabled"`` cleanly.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


DEFAULT_MODEL = "falai/flux-dev-lora"
DEFAULT_INFSH_BINARY = "infsh"


@dataclass
class StillResult:
    index: int
    prompt: str
    status: str  # "success" | "error" | "skipped"
    output_path: Optional[str] = None
    duration_s: Optional[float] = None
    error: Optional[str] = None


@dataclass
class StillsResult:
    status: str  # "success" | "partial" | "error" | "disabled" | "skipped"
    model: str
    stills: list[StillResult] = field(default_factory=list)
    total_duration_s: Optional[float] = None
    error: Optional[str] = None

    @property
    def success_count(self) -> int:
        return sum(1 for s in self.stills if s.status == "success")

    @property
    def artifacts(self) -> list[str]:
        return [s.output_path for s in self.stills if s.output_path]


class FluxStillsStage:
    """Run N FLUX still-image generations via the infsh CLI."""

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        binary: Optional[str] = None,
        aspect_ratio: str = "16:9",
        negative_prompt: str = "",
    ) -> None:
        self.model = model
        self.binary = binary or shutil.which(DEFAULT_INFSH_BINARY) or DEFAULT_INFSH_BINARY
        self.aspect_ratio = aspect_ratio
        self.negative_prompt = negative_prompt

    def is_available(self) -> bool:
        return shutil.which(self.binary) is not None

    def run(
        self,
        prompts: list[str],
        output_dir: Path,
        brand_negative_prompt: str = "",
    ) -> StillsResult:
        """Generate one still per prompt, writing to output_dir/still_N.png."""
        if not prompts:
            return StillsResult(
                status="skipped",
                model=self.model,
                error="no prompts supplied",
            )
        if not self.is_available():
            return StillsResult(
                status="disabled",
                model=self.model,
                error=(
                    f"{self.binary!r} not found on PATH. Install the "
                    "ai-image-generation skill's CLI first: "
                    "`curl -fsSL https://cli.inference.sh | sh && infsh login`"
                ),
            )

        output_dir.mkdir(parents=True, exist_ok=True)
        negative = ", ".join(
            p for p in (self.negative_prompt, brand_negative_prompt) if p
        )

        t0 = time.time()
        stills: list[StillResult] = []
        for i, prompt in enumerate(prompts):
            stills.append(
                self._run_one(
                    index=i,
                    prompt=prompt,
                    output_path=output_dir / f"still_{i}.png",
                    negative_prompt=negative,
                )
            )

        success = sum(1 for s in stills if s.status == "success")
        if success == len(stills):
            overall = "success"
        elif success == 0:
            overall = "error"
        else:
            overall = "partial"

        return StillsResult(
            status=overall,
            model=self.model,
            stills=stills,
            total_duration_s=round(time.time() - t0, 2),
        )

    def _run_one(
        self,
        index: int,
        prompt: str,
        output_path: Path,
        negative_prompt: str,
    ) -> StillResult:
        t0 = time.time()
        payload: dict[str, Any] = {
            "prompt": prompt,
            "aspect_ratio": self.aspect_ratio,
        }
        if negative_prompt:
            payload["negative_prompt"] = negative_prompt
        # Hint the CLI where to write the result if it honors the field.
        payload["output_path"] = str(output_path)

        cmd = [
            self.binary,
            "app",
            "run",
            self.model,
            "--input",
            json.dumps(payload),
        ]
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=600,
            )
        except Exception as exc:  # noqa: BLE001
            return StillResult(
                index=index,
                prompt=prompt,
                status="error",
                duration_s=round(time.time() - t0, 2),
                error=f"{type(exc).__name__}: {exc}",
            )

        if proc.returncode != 0:
            return StillResult(
                index=index,
                prompt=prompt,
                status="error",
                duration_s=round(time.time() - t0, 2),
                error=f"infsh exit {proc.returncode}: {proc.stderr[-600:]}",
            )

        # Try to resolve the final output path:
        #   1. If the CLI honored output_path, we're done.
        #   2. Otherwise, parse a URL or local path out of stdout.
        final_path: Optional[Path] = None
        if output_path.exists():
            final_path = output_path
        else:
            parsed = _extract_output_path(proc.stdout)
            if parsed is not None:
                parsed_path = Path(parsed)
                if parsed_path.exists() and parsed_path != output_path:
                    # Copy into the campaign dir
                    shutil.copy2(parsed_path, output_path)
                    final_path = output_path
                elif parsed.startswith(("http://", "https://")):
                    downloaded = _download(parsed, output_path)
                    if downloaded is not None:
                        final_path = downloaded

        if final_path is None:
            return StillResult(
                index=index,
                prompt=prompt,
                status="error",
                duration_s=round(time.time() - t0, 2),
                error=(
                    "infsh succeeded but no output file was produced at "
                    f"{output_path} and stdout contained no parseable "
                    "path. stdout tail: " + proc.stdout[-400:]
                ),
            )

        return StillResult(
            index=index,
            prompt=prompt,
            status="success",
            output_path=str(final_path),
            duration_s=round(time.time() - t0, 2),
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_URL_RX = re.compile(r"https?://[^\s'\"<>]+\.(?:png|jpg|jpeg|webp)", re.IGNORECASE)
_PATH_RX = re.compile(r"(?:/|[A-Za-z]:[\\/])[^\s'\"<>]+\.(?:png|jpg|jpeg|webp)")


def _extract_output_path(stdout: str) -> Optional[str]:
    """Extract the first image URL or absolute path from infsh stdout."""
    if not stdout:
        return None
    # Try JSON first
    try:
        obj = json.loads(stdout.strip().splitlines()[-1])
        if isinstance(obj, dict):
            for key in ("output", "output_path", "url", "image_url", "result"):
                val = obj.get(key)
                if isinstance(val, str):
                    return val
    except Exception:  # noqa: BLE001
        pass
    # Fall back to regex
    m = _URL_RX.search(stdout)
    if m:
        return m.group(0)
    m = _PATH_RX.search(stdout)
    if m:
        return m.group(0)
    return None


def _download(url: str, dest: Path) -> Optional[Path]:
    """Fetch a URL to ``dest`` via urllib. Returns None on failure."""
    try:
        import urllib.request

        dest.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(url, timeout=60) as resp:  # noqa: S310
            dest.write_bytes(resp.read())
        return dest
    except Exception:  # noqa: BLE001
        logger.debug("flux_stills: download failed for %s", url, exc_info=True)
        return None
