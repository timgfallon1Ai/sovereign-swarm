"""Model registry -- tracks locally available models."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import structlog

from sovereign_swarm.model_lab.models import ModelConfig

logger = structlog.get_logger()


class ModelRegistry:
    """Tracks all locally available models. Phase A: in-memory store. Phase B: SQLite."""

    def __init__(self) -> None:
        self._models: dict[str, ModelConfig] = {}

    def register(self, model: ModelConfig) -> ModelConfig:
        """Register a new model in the registry."""
        self._models[model.name] = model
        logger.info(
            "model_registry.registered",
            name=model.name,
            quantization=model.quantization,
            parameters_b=model.parameters_b,
        )
        return model

    def list_models(self, active_only: bool = False) -> list[ModelConfig]:
        """List all registered models."""
        models = list(self._models.values())
        if active_only:
            models = [m for m in models if m.active]
        return sorted(models, key=lambda m: m.name)

    def get_model(self, name: str) -> ModelConfig | None:
        """Get a specific model by name."""
        return self._models.get(name)

    def deactivate(self, name: str) -> bool:
        """Deactivate a model (mark as not in use)."""
        model = self._models.get(name)
        if model:
            model.active = False
            logger.info("model_registry.deactivated", name=name)
            return True
        return False

    def activate(self, name: str) -> bool:
        """Activate a model."""
        model = self._models.get(name)
        if model:
            model.active = True
            logger.info("model_registry.activated", name=name)
            return True
        return False

    def remove(self, name: str) -> bool:
        """Remove a model from the registry."""
        removed = self._models.pop(name, None)
        if removed:
            logger.info("model_registry.removed", name=name)
            return True
        return False

    def search(self, query: str) -> list[ModelConfig]:
        """Search models by name or tags."""
        query_lower = query.lower()
        return [
            m
            for m in self._models.values()
            if query_lower in m.name.lower()
            or any(query_lower in tag.lower() for tag in m.tags)
        ]
