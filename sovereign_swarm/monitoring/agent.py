"""MonitoringAgent -- observability agent for the Sovereign AI swarm."""

from __future__ import annotations

import asyncio
from typing import Any

import structlog

from sovereign_swarm.monitoring.models import ServiceStatus
from sovereign_swarm.protocol.swarm_agent import (
    SwarmAgent,
    SwarmAgentCard,
    SwarmAgentRequest,
    SwarmAgentResponse,
)

logger = structlog.get_logger()


class MonitoringAgent(SwarmAgent):
    """Monitors all services, tracks costs, and generates alerts."""

    def __init__(self, config: Any | None = None) -> None:
        self.config = config
        self._checker: Any | None = None
        self._cost_tracker: Any | None = None
        self._alert_manager: Any | None = None
        self._monitor_task: asyncio.Task[None] | None = None

    @property
    def card(self) -> SwarmAgentCard:
        return SwarmAgentCard(
            name="monitoring",
            description=(
                "Observability agent -- monitors service health, tracks API "
                "costs, generates alerts across the entire Sovereign AI ecosystem"
            ),
            domains=["monitoring", "observability", "health", "costs", "alerts"],
            supported_intents=[
                "health_check",
                "cost_report",
                "alert_status",
                "system_status",
            ],
            capabilities=[
                "health_check",
                "cost_tracking",
                "alerting",
                "system_snapshot",
            ],
        )

    async def execute(self, request: SwarmAgentRequest) -> SwarmAgentResponse:
        """Route monitoring requests to the appropriate handler."""
        task = request.task.lower()

        try:
            if "health" in task or "status" in task:
                result = await self._health_check()
            elif "cost" in task or "spend" in task:
                result = await self._cost_report()
            elif "alert" in task:
                result = await self._alert_report()
            elif "snapshot" in task or "overview" in task:
                result = await self._full_snapshot()
            else:
                result = await self._full_snapshot()

            return SwarmAgentResponse(
                agent_name="monitoring",
                status="success",
                output=result.get("markdown", str(result)),
                data=result,
                confidence=0.9,
            )
        except Exception as e:
            logger.error("monitoring.execute_failed", error=str(e))
            return SwarmAgentResponse(
                agent_name="monitoring",
                status="error",
                error=str(e),
            )

    # ------------------------------------------------------------------
    # Report generators
    # ------------------------------------------------------------------

    async def _health_check(self) -> dict:
        checker = self._get_checker()
        checks = await checker.check_all()

        # Also generate alerts from the checks
        alert_mgr = self._get_alert_manager()
        await alert_mgr.check_and_alert(checks, self._get_cost_tracker())

        healthy = sum(1 for c in checks if c.status == ServiceStatus.HEALTHY)
        total = len(checks)

        lines = [f"## System Health: {healthy}/{total} services healthy\n"]
        for c in checks:
            if c.status == ServiceStatus.HEALTHY:
                icon = "green"
            elif c.status == ServiceStatus.DEGRADED:
                icon = "yellow"
            else:
                icon = "red"
            line = f"- [{icon}] **{c.service_name}**: {c.status.value}"
            if c.response_time_ms:
                line += f" ({c.response_time_ms:.0f}ms)"
            if c.error:
                line += f" -- {c.error}"
            lines.append(line)

        markdown = "\n".join(lines)
        return {
            "markdown": markdown,
            "checks": [c.model_dump() for c in checks],
            "healthy": healthy,
            "total": total,
        }

    async def _cost_report(self) -> dict:
        tracker = self._get_cost_tracker()
        daily = await tracker.get_daily_cost()
        by_agent = await tracker.get_cost_by_agent()
        by_service = await tracker.get_cost_by_service()

        lines = [
            "## Cost Report\n",
            f"**Today's spend**: ${daily:.2f}\n",
        ]
        if by_agent:
            lines.append("**By agent**:")
            for agent, cost in sorted(
                by_agent.items(), key=lambda x: x[1], reverse=True
            ):
                lines.append(f"  - {agent}: ${cost:.4f}")
        if by_service:
            lines.append("**By service**:")
            for svc, cost in sorted(
                by_service.items(), key=lambda x: x[1], reverse=True
            ):
                lines.append(f"  - {svc}: ${cost:.4f}")

        markdown = "\n".join(lines)
        return {
            "markdown": markdown,
            "daily_cost": daily,
            "by_agent": by_agent,
            "by_service": by_service,
        }

    async def _alert_report(self) -> dict:
        alerts = await self._get_alert_manager().get_active_alerts()

        lines = [f"## Active Alerts: {len(alerts)}\n"]
        for a in alerts:
            if a.severity == "critical":
                icon = "CRITICAL"
            elif a.severity == "warning":
                icon = "WARNING"
            else:
                icon = "INFO"
            lines.append(f"- [{icon}] **{a.source}**: {a.message}")

        if not alerts:
            lines.append("No active alerts.")

        markdown = "\n".join(lines)
        return {
            "markdown": markdown,
            "alerts": [a.model_dump() for a in alerts],
        }

    async def _full_snapshot(self) -> dict:
        health = await self._health_check()
        costs = await self._cost_report()
        alerts = await self._alert_report()

        markdown = (
            "# Sovereign AI System Snapshot\n\n"
            f"{health['markdown']}\n\n"
            f"{costs['markdown']}\n\n"
            f"{alerts['markdown']}"
        )
        return {
            "markdown": markdown,
            "health": health,
            "costs": costs,
            "alerts": alerts,
        }

    # ------------------------------------------------------------------
    # Background monitoring
    # ------------------------------------------------------------------

    async def start_background_monitoring(
        self, interval_seconds: int = 300
    ) -> None:
        """Start background monitoring loop (default: every 5 min)."""
        if self._monitor_task and not self._monitor_task.done():
            logger.info("monitoring.already_running")
            return
        self._monitor_task = asyncio.create_task(
            self._monitor_loop(interval_seconds)
        )
        logger.info(
            "monitoring.background_started", interval=interval_seconds
        )

    async def stop_background_monitoring(self) -> None:
        """Cancel the background monitoring loop."""
        if self._monitor_task and not self._monitor_task.done():
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
            logger.info("monitoring.background_stopped")

    async def _monitor_loop(self, interval: int) -> None:
        """Continuous monitoring loop."""
        while True:
            try:
                checker = self._get_checker()
                checks = await checker.check_all()
                await self._get_alert_manager().check_and_alert(
                    checks, self._get_cost_tracker()
                )
                healthy = sum(
                    1 for c in checks if c.status == ServiceStatus.HEALTHY
                )
                logger.info(
                    "monitoring.loop_tick",
                    healthy=healthy,
                    total=len(checks),
                )
            except Exception as e:
                logger.error("monitoring.loop_error", error=str(e))
            await asyncio.sleep(interval)

    # ------------------------------------------------------------------
    # Lazy component accessors
    # ------------------------------------------------------------------

    def _get_checker(self):
        if self._checker is None:
            from sovereign_swarm.monitoring.health_checker import HealthChecker

            self._checker = HealthChecker(self.config)
        return self._checker

    def _get_cost_tracker(self):
        if self._cost_tracker is None:
            from sovereign_swarm.monitoring.cost_tracker import CostTracker

            self._cost_tracker = CostTracker()
        return self._cost_tracker

    def _get_alert_manager(self):
        if self._alert_manager is None:
            from sovereign_swarm.monitoring.alert_manager import AlertManager

            self._alert_manager = AlertManager()
        return self._alert_manager
