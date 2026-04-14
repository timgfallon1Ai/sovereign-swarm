"""IntelScheduler — manages cadence for strategic intel runs per tenant."""

from __future__ import annotations

import asyncio
import json
import structlog
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from sovereign_swarm.strategic_intel.agent import StrategicIntelAgent

logger = structlog.get_logger()

_DEFAULT_INTERVAL = 7 * 24 * 3600  # 7 days
_POLL_INTERVAL = 3600  # check every hour


class IntelScheduler:
    """Manages weekly cadence for strategic intel runs per tenant."""

    def __init__(
        self,
        agent: StrategicIntelAgent,
        interval_seconds: int = _DEFAULT_INTERVAL,
        poll_seconds: float = _POLL_INTERVAL,
        data_dir: str | Path = "data/strategic_intel",
    ) -> None:
        self._agent = agent
        self._interval = interval_seconds
        self._poll = poll_seconds
        self._data_dir = Path(str(data_dir)).expanduser()
        self._last_runs: dict[str, datetime] = {}
        self._running = False
        self._task: asyncio.Task[None] | None = None
        self._load_last_runs()

    async def start(self, tenants: list[str] | None = None) -> None:
        """Start the scheduler for specified tenants (default: all)."""
        if tenants is None:
            from sovereign_swarm.marketing.brand import TENANTS
            tenants = list(TENANTS.keys())

        self._tenants = tenants
        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info("intel_scheduler.started", tenants=tenants)

    async def stop(self) -> None:
        """Gracefully stop the scheduler."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("intel_scheduler.stopped")

    async def trigger_now(
        self,
        tenant: str,
        tier: str = "tier_1",
    ) -> dict[str, Any]:
        """Manual trigger for on-demand runs."""
        from sovereign_swarm.protocol.swarm_agent import SwarmAgentRequest

        request = SwarmAgentRequest(
            task="weekly_intel_cycle",
            parameters={"tenant": tenant, "tier": tier},
        )
        response = await self._agent.execute(request)
        self._save_last_run(tenant)
        return response.data or {}

    async def _run_loop(self) -> None:
        """Background loop: check if any tenant is due for a run."""
        while self._running:
            for tenant in self._tenants:
                if await self._is_due(tenant):
                    logger.info("intel_scheduler.triggering", tenant=tenant)
                    try:
                        await self.trigger_now(tenant, tier="tier_1")
                    except Exception as exc:
                        logger.error(
                            "intel_scheduler.run_failed",
                            tenant=tenant,
                            error=str(exc),
                        )
            await asyncio.sleep(self._poll)

    async def _is_due(self, tenant: str) -> bool:
        """Check if enough time has passed since last run."""
        last = self._last_runs.get(tenant)
        if last is None:
            return True
        return datetime.utcnow() - last >= timedelta(seconds=self._interval)

    def _load_last_runs(self) -> None:
        """Load last run timestamps from disk."""
        for tenant_dir in self._data_dir.glob("*/"):
            ts_file = tenant_dir / "last_run.json"
            if ts_file.exists():
                try:
                    data = json.loads(ts_file.read_text())
                    self._last_runs[tenant_dir.name] = datetime.fromisoformat(
                        data["last_run"]
                    )
                except Exception:
                    pass

    def _save_last_run(self, tenant: str) -> None:
        """Persist last run timestamp."""
        self._last_runs[tenant] = datetime.utcnow()
        tenant_dir = self._data_dir / tenant
        tenant_dir.mkdir(parents=True, exist_ok=True)
        ts_file = tenant_dir / "last_run.json"
        ts_file.write_text(
            json.dumps({"last_run": datetime.utcnow().isoformat()})
        )
