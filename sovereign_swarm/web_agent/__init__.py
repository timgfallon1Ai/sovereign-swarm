"""Web / GUI visual understanding agent backed by UI-TARS-1.5-7B-4bit MLX."""
from sovereign_swarm.web_agent.agent import WebAgent
from sovereign_swarm.web_agent.backend import (
    DEFAULT_MODEL,
    FALLBACK_MODEL,
    UITarsBackend,
    VLMResponse,
)

__all__ = [
    "WebAgent",
    "UITarsBackend",
    "VLMResponse",
    "DEFAULT_MODEL",
    "FALLBACK_MODEL",
]
