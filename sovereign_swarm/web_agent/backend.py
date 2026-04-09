"""UI-TARS MLX backend — the actual VLM wrapper.

Kept separate from the SwarmAgent wrapper so it can be reused outside
the swarm (e.g. from sovereign-video, ATS-Trading-Ai, standalone scripts).

Requires `mlx-vlm` to be installed in the active venv. The import is lazy
so importing this module does not pull MLX into environments that don't
need it.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Auto-route HF downloads to T7 Shield if mounted, so the sovereign ecosystem
# doesn't duplicate models on the internal SSD. .zshrc sets HF_HOME for
# interactive shells but non-interactive python invocations don't inherit it,
# which is why we also check here.
_T7_HF = Path("/Volumes/T7_Shield/sovereign-data/huggingface")
if _T7_HF.exists() and not os.environ.get("HF_HOME"):
    os.environ["HF_HOME"] = str(_T7_HF)
    os.environ.setdefault("HF_HUB_CACHE", str(_T7_HF / "hub"))

DEFAULT_MODEL = "mlx-community/UI-TARS-1.5-7B-4bit"
FALLBACK_MODEL = "mlx-community/Qwen2.5-VL-7B-Instruct-4bit"

# UI-TARS emits grounding coordinates in a specific token format;
# this pulls the (x, y) tuple out of either format the family uses.
_BOX_RX = re.compile(r"<\|box_start\|>\s*\(?\s*(\d+)\s*,\s*(\d+)\s*\)?\s*<\|box_end\|>")
_PAREN_RX = re.compile(r"\(\s*(\d+)\s*,\s*(\d+)\s*\)")


@dataclass
class VLMResponse:
    text: str
    model: str
    time_s: float
    n_tokens: int = 0
    tok_s: float = 0.0
    coordinates: tuple[int, int] | None = None
    raw: Any = field(default=None, repr=False)


class UITarsBackend:
    """Lazy-loaded UI-TARS-1.5-7B-4bit MLX backend.

    The model is loaded on first call, then kept resident. Call `unload()`
    to free memory. Multiple prompts per load are cheap.
    """

    def __init__(self, model_path: str = DEFAULT_MODEL) -> None:
        self.model_path = model_path
        self._model: Any = None
        self._processor: Any = None
        self._config: Any = None

    def _ensure_loaded(self) -> None:
        if self._model is not None:
            return
        try:
            from mlx_vlm import load
            from mlx_vlm.utils import load_config
        except ImportError as exc:
            raise RuntimeError(
                "mlx-vlm not installed. Install in this venv or run from "
                "sovereign-video/.venv which already has it: pip install mlx-vlm"
            ) from exc
        self._model, self._processor = load(self.model_path)
        self._config = load_config(self.model_path)

    def unload(self) -> None:
        self._model = None
        self._processor = None
        self._config = None
        try:
            import gc
            import mlx.core as mx
            gc.collect()
            mx.clear_cache()
        except Exception:
            pass

    def _generate(
        self,
        prompt: str,
        image_path: str | Path,
        max_tokens: int = 128,
    ) -> VLMResponse:
        import time

        from mlx_vlm import generate
        from mlx_vlm.prompt_utils import apply_chat_template

        self._ensure_loaded()
        assert self._processor is not None
        assert self._model is not None

        formatted = apply_chat_template(
            self._processor, self._config, prompt, num_images=1
        )
        t0 = time.time()
        out = generate(
            self._model,
            self._processor,
            formatted,
            [str(image_path)],
            max_tokens=max_tokens,
            verbose=False,
        )
        dt = time.time() - t0

        text = getattr(out, "text", None) or (out[0] if isinstance(out, tuple) else str(out))
        n_tok = (
            getattr(out, "generation_tokens", None)
            or getattr(out, "num_tokens", None)
            or len(text.split())
        )
        coords = self._extract_coordinates(text)
        return VLMResponse(
            text=text,
            model=self.model_path,
            time_s=round(dt, 2),
            n_tokens=int(n_tok) if n_tok else 0,
            tok_s=round((n_tok / dt), 2) if n_tok and dt > 0 else 0.0,
            coordinates=coords,
            raw=out,
        )

    @staticmethod
    def _extract_coordinates(text: str) -> tuple[int, int] | None:
        """Parse UI-TARS `<|box_start|>(x,y)<|box_end|>` or plain `(x, y)`."""
        m = _BOX_RX.search(text)
        if m:
            return int(m.group(1)), int(m.group(2))
        m = _PAREN_RX.search(text)
        if m:
            return int(m.group(1)), int(m.group(2))
        return None

    # -- Public API -------------------------------------------------------

    def describe(self, image_path: str | Path, max_tokens: int = 128) -> VLMResponse:
        """General description of an image or UI screenshot."""
        return self._generate(
            "Describe what is visible in this image in 2-3 sentences.",
            image_path,
            max_tokens=max_tokens,
        )

    def locate(
        self,
        image_path: str | Path,
        element_description: str,
        max_tokens: int = 48,
    ) -> VLMResponse:
        """Ground a natural-language element description to pixel coordinates.

        Returns a VLMResponse with `.coordinates` populated as (x, y) on success.
        Works best on UI-TARS due to its explicit bbox training.
        """
        prompt = (
            f"Locate the {element_description} in this screenshot. "
            f"Respond with just the pixel coordinates as (x, y)."
        )
        return self._generate(prompt, image_path, max_tokens=max_tokens)

    def answer(
        self,
        image_path: str | Path,
        question: str,
        max_tokens: int = 256,
    ) -> VLMResponse:
        """Free-form visual question answering."""
        return self._generate(question, image_path, max_tokens=max_tokens)
