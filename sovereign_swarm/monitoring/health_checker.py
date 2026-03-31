"""Health checker -- monitors all services in the Sovereign AI ecosystem."""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

import structlog

from sovereign_swarm.monitoring.models import ServiceCheck, ServiceStatus

logger = structlog.get_logger()


class HealthChecker:
    """Monitors health of all services in the Sovereign AI ecosystem."""

    def __init__(self, config: Any | None = None) -> None:
        self.config = config
        self._checks: dict[str, ServiceCheck] = {}

    async def check_all(self) -> list[ServiceCheck]:
        """Run all health checks concurrently."""
        checks = await asyncio.gather(
            self._check_redis(),
            self._check_postgresql(),
            self._check_chromadb(),
            self._check_sovereign_ai(),
            self._check_sovereign_ingest(),
            self._check_ats(),
            self._check_railway_services(),
            return_exceptions=True,
        )
        results: list[ServiceCheck] = []
        for check in checks:
            if isinstance(check, Exception):
                results.append(
                    ServiceCheck(
                        service_name="unknown",
                        status=ServiceStatus.DOWN,
                        error=str(check),
                    )
                )
            elif isinstance(check, list):
                results.extend(check)
            elif check is not None:
                results.append(check)
        self._checks = {c.service_name: c for c in results}
        return results

    @property
    def last_checks(self) -> dict[str, ServiceCheck]:
        return dict(self._checks)

    # ------------------------------------------------------------------
    # Individual service checks
    # ------------------------------------------------------------------

    async def _check_redis(self) -> ServiceCheck:
        """Ping Redis."""
        try:
            import redis.asyncio as aioredis

            from sovereign_swarm.config import get_settings

            settings = get_settings()
            start = datetime.utcnow()
            r = aioredis.from_url(settings.redis_url)
            await r.ping()
            await r.aclose()
            ms = (datetime.utcnow() - start).total_seconds() * 1000
            return ServiceCheck(
                service_name="redis",
                status=ServiceStatus.HEALTHY,
                response_time_ms=ms,
            )
        except Exception as e:
            return ServiceCheck(
                service_name="redis",
                status=ServiceStatus.DOWN,
                error=str(e),
            )

    async def _check_postgresql(self) -> ServiceCheck:
        """Check PostgreSQL connectivity."""
        try:
            import asyncpg

            from sovereign_swarm.config import get_settings

            settings = get_settings()
            start = datetime.utcnow()
            conn = await asyncpg.connect(settings.database_url, timeout=5)
            await conn.fetchval("SELECT 1")
            await conn.close()
            ms = (datetime.utcnow() - start).total_seconds() * 1000
            return ServiceCheck(
                service_name="postgresql",
                status=ServiceStatus.HEALTHY,
                response_time_ms=ms,
            )
        except Exception as e:
            return ServiceCheck(
                service_name="postgresql",
                status=ServiceStatus.DOWN,
                error=str(e),
            )

    async def _check_chromadb(self) -> ServiceCheck:
        """Check ChromaDB availability and document counts."""
        try:
            import sys

            from sovereign_swarm.config import get_settings

            settings = get_settings()
            ingest_path = str(settings.sovereign_ingest_path)
            if ingest_path not in sys.path:
                sys.path.insert(0, ingest_path)

            from sovereign_ingest.config import get_settings as get_ingest_settings

            ingest_settings = get_ingest_settings()
            start = datetime.utcnow()

            import chromadb

            client = chromadb.PersistentClient(path=str(ingest_settings.chroma_dir))
            collections = client.list_collections()
            ms = (datetime.utcnow() - start).total_seconds() * 1000
            total_docs = sum(c.count() for c in collections)
            return ServiceCheck(
                service_name="chromadb",
                status=ServiceStatus.HEALTHY,
                response_time_ms=ms,
                metadata={
                    "collections": len(collections),
                    "total_chunks": total_docs,
                },
            )
        except Exception as e:
            return ServiceCheck(
                service_name="chromadb",
                status=ServiceStatus.DOWN,
                error=str(e),
            )

    async def _check_sovereign_ai(self) -> ServiceCheck:
        """Check if sovereign-ai FastAPI is responding."""
        try:
            import httpx

            start = datetime.utcnow()
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get("http://localhost:8000/health")
                ms = (datetime.utcnow() - start).total_seconds() * 1000
                if resp.status_code == 200:
                    return ServiceCheck(
                        service_name="sovereign-ai",
                        status=ServiceStatus.HEALTHY,
                        response_time_ms=ms,
                        metadata=resp.json(),
                    )
                return ServiceCheck(
                    service_name="sovereign-ai",
                    status=ServiceStatus.DEGRADED,
                    response_time_ms=ms,
                    error=f"HTTP {resp.status_code}",
                )
        except Exception as e:
            return ServiceCheck(
                service_name="sovereign-ai",
                status=ServiceStatus.DOWN,
                error=str(e),
            )

    async def _check_sovereign_ingest(self) -> ServiceCheck:
        """Check sovereign-ingest MCP server availability."""
        try:
            import sys

            from sovereign_swarm.config import get_settings

            settings = get_settings()
            ingest_path = str(settings.sovereign_ingest_path)
            if ingest_path not in sys.path:
                sys.path.insert(0, ingest_path)

            start = datetime.utcnow()
            from sovereign_ingest.mcp_server.tools import ingest_get_stats

            stats = await ingest_get_stats()
            ms = (datetime.utcnow() - start).total_seconds() * 1000
            return ServiceCheck(
                service_name="sovereign-ingest",
                status=ServiceStatus.HEALTHY,
                response_time_ms=ms,
                metadata=stats if isinstance(stats, dict) else {},
            )
        except Exception as e:
            return ServiceCheck(
                service_name="sovereign-ingest",
                status=ServiceStatus.DOWN,
                error=str(e),
            )

    async def _check_ats(self) -> ServiceCheck:
        """Check ATS Trading API."""
        try:
            import httpx

            start = datetime.utcnow()
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get("http://localhost:8081/health")
                ms = (datetime.utcnow() - start).total_seconds() * 1000
                if resp.status_code == 200:
                    return ServiceCheck(
                        service_name="ats-trading",
                        status=ServiceStatus.HEALTHY,
                        response_time_ms=ms,
                    )
                return ServiceCheck(
                    service_name="ats-trading",
                    status=ServiceStatus.DEGRADED,
                    response_time_ms=ms,
                    error=f"HTTP {resp.status_code}",
                )
        except Exception as e:
            return ServiceCheck(
                service_name="ats-trading",
                status=ServiceStatus.DOWN,
                error=str(e),
            )

    async def _check_railway_services(self) -> list[ServiceCheck]:
        """Check Railway-deployed services."""
        services = {
            "gbb-system": "https://gbb-ai-agent-system-production.up.railway.app/health",
        }
        checks: list[ServiceCheck] = []
        for name, url in services.items():
            try:
                import httpx

                start = datetime.utcnow()
                async with httpx.AsyncClient(timeout=10) as client:
                    resp = await client.get(url)
                    ms = (datetime.utcnow() - start).total_seconds() * 1000
                    status = (
                        ServiceStatus.HEALTHY
                        if resp.status_code == 200
                        else ServiceStatus.DEGRADED
                    )
                    checks.append(
                        ServiceCheck(
                            service_name=name,
                            status=status,
                            response_time_ms=ms,
                        )
                    )
            except Exception as e:
                checks.append(
                    ServiceCheck(
                        service_name=name,
                        status=ServiceStatus.DOWN,
                        error=str(e),
                    )
                )
        return checks
