"""Swarm configuration via pydantic-settings."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings


class SwarmSettings(BaseSettings):
    """Central configuration for sovereign-swarm."""

    model_config = {"env_prefix": "", "env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}

    # --- API keys & connections ---
    anthropic_api_key: str = ""
    redis_url: str = "redis://localhost:6379/1"
    database_url: str = "postgresql://postgres:postgres@localhost:5432/sovereign"
    jwt_secret_key: str = ""

    # --- Sibling repo paths ---
    sovereign_ai_path: Path = Path("/Users/timothyfallon/Documents/GitHub/sovereign-ai")
    sovereign_ingest_path: Path = Path("/Users/timothyfallon/Documents/GitHub/sovereign-ingest")

    # --- Model selection ---
    fast_model: str = "claude-haiku-4-5-20251001"
    slow_model: str = "claude-haiku-4-5-20251001"  # Sonnet not on this API key — use Haiku until upgraded
    coordinator_model: str = "claude-haiku-4-5-20251001"

    # --- Runtime ---
    max_concurrency: int = 5
    idle_threshold_seconds: int = 300
    data_dir: Path = Path("./data")


@lru_cache(maxsize=1)
def get_settings() -> SwarmSettings:
    """Return a singleton SwarmSettings instance."""
    return SwarmSettings()
