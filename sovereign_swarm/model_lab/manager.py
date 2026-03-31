"""Model lifecycle management -- download, quantize, A/B test, promote, rollback."""

from __future__ import annotations

from typing import Any

import structlog

from sovereign_swarm.model_lab.models import ModelConfig

logger = structlog.get_logger()


class ModelManager:
    """Handles model lifecycle: download, quantize, promote, rollback.

    Phase A: stubs for download/quantize (needs Mac Studio hardware).
    Phase B: activates real inference with huggingface-cli and bitsandbytes/llama.cpp.
    """

    def __init__(self, registry: Any | None = None) -> None:
        self._registry = registry
        self._default_models: dict[str, str] = {}  # capability -> model_name
        self._promotion_history: list[dict[str, Any]] = []

    async def download_model(
        self,
        repo_id: str,
        quantization: str = "",
        name: str = "",
    ) -> dict[str, Any]:
        """Download a model from HuggingFace (Phase A: stub).

        Phase B: uses huggingface-cli download.
        """
        model_name = name or repo_id.split("/")[-1]
        logger.info(
            "model_manager.download_stub",
            repo_id=repo_id,
            quantization=quantization,
        )

        # Phase A: register metadata without actual download
        config = ModelConfig(
            name=model_name,
            path=f"~/.cache/huggingface/hub/{repo_id.replace('/', '--')}",
            quantization=quantization,
            tags=["downloaded", "phase_a_stub"],
            metadata={"repo_id": repo_id, "downloaded": False},
        )

        if self._registry:
            self._registry.register(config)

        return {
            "status": "stub",
            "message": (
                f"Model {repo_id} queued for download. "
                "Phase A: metadata registered. "
                "Phase B: will download via huggingface-cli on Mac Studio."
            ),
            "model": config.model_dump(),
        }

    async def quantize_model(
        self,
        model_name: str,
        quantization: str = "4bit",
        method: str = "bitsandbytes",
    ) -> dict[str, Any]:
        """Quantize a model (Phase A: stub).

        Phase B: uses bitsandbytes (GPU) or llama.cpp (GGUF).
        """
        logger.info(
            "model_manager.quantize_stub",
            model=model_name,
            quantization=quantization,
            method=method,
        )

        return {
            "status": "stub",
            "message": (
                f"Model {model_name} queued for {quantization} quantization via {method}. "
                "Phase A: not yet available. "
                "Phase B: will quantize on Mac Studio."
            ),
        }

    def promote(self, model_name: str, capability: str) -> dict[str, Any]:
        """Promote a model as the default for a capability."""
        previous = self._default_models.get(capability)
        self._default_models[capability] = model_name

        self._promotion_history.append(
            {
                "capability": capability,
                "new_model": model_name,
                "previous_model": previous,
            }
        )

        logger.info(
            "model_manager.promoted",
            model=model_name,
            capability=capability,
            previous=previous,
        )

        return {
            "capability": capability,
            "model": model_name,
            "previous": previous,
        }

    def rollback(self, capability: str) -> dict[str, Any]:
        """Rollback to the previous model for a capability."""
        # Find the last promotion for this capability
        for entry in reversed(self._promotion_history):
            if entry["capability"] == capability and entry["previous_model"]:
                previous = entry["previous_model"]
                self._default_models[capability] = previous
                logger.info(
                    "model_manager.rollback",
                    capability=capability,
                    rolled_back_to=previous,
                )
                return {
                    "capability": capability,
                    "rolled_back_to": previous,
                }

        return {
            "capability": capability,
            "error": "No previous model found for rollback",
        }

    def get_default_model(self, capability: str) -> str | None:
        """Get the default model for a capability."""
        return self._default_models.get(capability)

    def get_defaults(self) -> dict[str, str]:
        """Return all default model assignments."""
        return dict(self._default_models)
