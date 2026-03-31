"""Generates training data from swarm interactions and skill modules."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import orjson
import structlog

from sovereign_swarm.integration.ingest_bridge import SovereignIngestBridge

logger = structlog.get_logger()


class TrainingPipeline:
    """Generates training data from swarm interactions and skill modules."""

    def __init__(
        self,
        ingest_bridge: SovereignIngestBridge | None = None,
        data_dir: str = "./data",
    ):
        self.ingest = ingest_bridge
        self.data_dir = Path(data_dir) / "training"
        self.data_dir.mkdir(parents=True, exist_ok=True)

    async def generate_from_interactions(
        self, interactions: list[dict], min_confidence: float = 0.7
    ) -> list[dict]:
        """Generate JSONL training records from successful interactions."""
        records = []
        for ix in interactions:
            if ix.get("confidence", 0) < min_confidence:
                continue
            records.append(
                {
                    "instruction": ix.get("task", ""),
                    "input": orjson.dumps(ix.get("context", {})).decode(),
                    "output": ix.get("output", ""),
                    "source": "swarm_interaction",
                    "agent": ix.get("agent_name", ""),
                    "confidence": ix.get("confidence", 0),
                }
            )
        return records

    async def generate_from_modules(
        self, modules: list[dict],
    ) -> list[dict]:
        """Generate JSONL from consolidated skill modules."""
        records = []
        for m in modules:
            if hasattr(m, "training_data"):
                records.extend(m.training_data)
            else:
                records.extend(m.get("training_data", []))
        return records

    async def export_jsonl(
        self, records: list[dict], filename: str = ""
    ) -> str:
        """Write records to JSONL file."""
        if not filename:
            filename = (
                f"swarm_training_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.jsonl"
            )
        path = self.data_dir / filename
        with open(path, "wb") as f:
            for record in records:
                f.write(orjson.dumps(record))
                f.write(b"\n")
        logger.info("training.exported", path=str(path), records=len(records))
        return str(path)
