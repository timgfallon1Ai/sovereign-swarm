"""Alert manager -- generates, deduplicates, and routes alerts."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

import structlog

from sovereign_swarm.monitoring.models import Alert, ServiceCheck, ServiceStatus

if TYPE_CHECKING:
    from sovereign_swarm.monitoring.cost_tracker import CostTracker

logger = structlog.get_logger()


class AlertManager:
    """Generates and manages alerts for the ecosystem."""

    def __init__(self, db_path: str = "data/monitoring/alerts.db") -> None:
        self.db_path = db_path
        self._active_alerts: list[Alert] = []
        self._initialized = False

    async def initialize(self) -> None:
        """Create SQLite table for alert persistence."""
        if self._initialized:
            return
        path = Path(self.db_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(path))
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS alerts (
                id TEXT PRIMARY KEY,
                severity TEXT NOT NULL,
                source TEXT NOT NULL,
                message TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                acknowledged INTEGER DEFAULT 0,
                resolved INTEGER DEFAULT 0,
                metadata TEXT DEFAULT '{}'
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_alerts_source ON alerts(source)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_alerts_resolved ON alerts(resolved)"
        )
        conn.commit()
        conn.close()
        self._initialized = True
        logger.info("alert_manager.initialized", db_path=self.db_path)

    async def check_and_alert(
        self,
        checks: list[ServiceCheck],
        cost_tracker: CostTracker | None = None,
    ) -> list[Alert]:
        """Generate alerts from health checks and cost data."""
        new_alerts: list[Alert] = []

        for check in checks:
            if check.status == ServiceStatus.DOWN:
                alert = await self.create_alert(
                    "critical",
                    check.service_name,
                    f"{check.service_name} is DOWN: {check.error}",
                )
                if alert:
                    new_alerts.append(alert)
            elif check.status == ServiceStatus.DEGRADED:
                alert = await self.create_alert(
                    "warning",
                    check.service_name,
                    f"{check.service_name} degraded: {check.error}",
                )
                if alert:
                    new_alerts.append(alert)
            elif check.response_time_ms > 5000:
                alert = await self.create_alert(
                    "warning",
                    check.service_name,
                    f"{check.service_name} slow response: {check.response_time_ms:.0f}ms",
                )
                if alert:
                    new_alerts.append(alert)

        # Cost alerts
        if cost_tracker:
            daily = await cost_tracker.get_daily_cost()
            if daily > 50:
                alert = await self.create_alert(
                    "critical",
                    "costs",
                    f"Daily API cost exceeds $50: ${daily:.2f}",
                )
                if alert:
                    new_alerts.append(alert)
            elif daily > 20:
                alert = await self.create_alert(
                    "warning",
                    "costs",
                    f"Daily API cost high: ${daily:.2f}",
                )
                if alert:
                    new_alerts.append(alert)

        return new_alerts

    async def create_alert(
        self,
        severity: str,
        source: str,
        message: str,
        metadata: dict | None = None,
    ) -> Alert | None:
        """Create an alert, deduplicating against recent active alerts."""
        # Deduplicate: skip if same source+message is active in the last hour
        cutoff = datetime.utcnow() - timedelta(hours=1)
        for existing in self._active_alerts:
            if (
                existing.source == source
                and existing.message == message
                and not existing.resolved
                and existing.timestamp >= cutoff
            ):
                return None

        alert = Alert(
            severity=severity,
            source=source,
            message=message,
            metadata=metadata or {},
        )
        self._active_alerts.append(alert)
        logger.warning(
            "alert_manager.new_alert",
            severity=severity,
            source=source,
            message=message,
        )
        return alert

    async def get_active_alerts(self) -> list[Alert]:
        """Return all unresolved alerts."""
        return [a for a in self._active_alerts if not a.resolved]

    async def acknowledge(self, alert_id: str) -> bool:
        """Acknowledge an alert by ID."""
        for alert in self._active_alerts:
            if alert.id == alert_id:
                alert.acknowledged = True
                logger.info("alert_manager.acknowledged", alert_id=alert_id)
                return True
        return False

    async def resolve(self, alert_id: str) -> bool:
        """Resolve an alert by ID."""
        for alert in self._active_alerts:
            if alert.id == alert_id:
                alert.resolved = True
                logger.info("alert_manager.resolved", alert_id=alert_id)
                return True
        return False

    async def resolve_by_source(self, source: str) -> int:
        """Resolve all active alerts for a given source."""
        count = 0
        for alert in self._active_alerts:
            if alert.source == source and not alert.resolved:
                alert.resolved = True
                count += 1
        if count:
            logger.info(
                "alert_manager.resolved_by_source", source=source, count=count
            )
        return count
