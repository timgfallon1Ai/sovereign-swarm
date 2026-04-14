"""InternalMirror — snapshots internal business state for gap comparison.

This is the MIRROR phase: captures what the business currently believes
about itself from the sovereign-ingest KB, brand profiles, and financial data.
The output gets compared against external signals to detect gaps.
"""

from __future__ import annotations

import structlog
from dataclasses import asdict
from typing import Any

from sovereign_swarm.strategic_intel.models import InternalSnapshot

logger = structlog.get_logger()


class InternalMirror:
    """Snapshots internal state from KB, brand profiles, and financials."""

    def __init__(self) -> None:
        self._ingest_bridge = None

    async def snapshot(self, tenant: str) -> InternalSnapshot:
        """Build a complete internal state snapshot for a tenant."""
        brand_profile = self._get_brand_context(tenant)
        kb_excerpts = await self._query_kb_for_tenant(tenant, brand_profile)
        assumptions = self._extract_assumptions(brand_profile, kb_excerpts)

        return InternalSnapshot(
            tenant=tenant,
            brand_profile=brand_profile,
            kb_excerpts=kb_excerpts,
            current_assumptions=assumptions,
        )

    def _get_brand_context(self, tenant: str) -> dict[str, Any]:
        """Load TenantBrand as a dict."""
        try:
            from sovereign_swarm.marketing.brand import get_brand
            brand = get_brand(tenant)
            return {
                "key": brand.key,
                "display_name": brand.display_name,
                "tagline": brand.tagline,
                "one_liner": brand.one_liner,
                "target_audience": brand.target_audience,
                "tone_keywords": list(brand.tone_keywords),
                "palette": list(brand.palette),
                "domain": brand.domain,
                "notes": brand.notes,
            }
        except KeyError:
            logger.warning("mirror.brand_not_found", tenant=tenant)
            return {"key": tenant, "display_name": tenant}

    async def _query_kb_for_tenant(
        self, tenant: str, brand_profile: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Query sovereign-ingest for tenant-relevant knowledge."""
        bridge = self._get_bridge()
        if not bridge or not bridge.available:
            return []

        display = brand_profile.get("display_name", tenant)
        audience = brand_profile.get("target_audience", "")
        one_liner = brand_profile.get("one_liner", "")

        queries = [
            f"{display} market position competitors",
            f"{display} customers revenue pricing",
            f"{audience} industry trends",
        ]

        excerpts: list[dict[str, Any]] = []
        for q in queries:
            try:
                results = await bridge.search(q, limit=3)
                for r in results.get("results", []):
                    excerpts.append({
                        "query": q,
                        "title": r.get("document_title", ""),
                        "source": r.get("source", ""),
                        "text": r.get("chunk_text", "")[:500],
                        "score": r.get("score", 0.0),
                    })
            except Exception as exc:
                logger.debug("mirror.kb_query_failed", query=q, error=str(exc))

        return excerpts

    @staticmethod
    def _extract_assumptions(
        brand_profile: dict[str, Any],
        kb_excerpts: list[dict[str, Any]],
    ) -> list[str]:
        """Derive current assumptions from brand profile and KB."""
        assumptions = []

        # From brand profile
        if brand_profile.get("target_audience"):
            assumptions.append(
                f"Our target audience is: {brand_profile['target_audience'][:200]}"
            )
        if brand_profile.get("one_liner"):
            assumptions.append(
                f"Our positioning: {brand_profile['one_liner'][:200]}"
            )
        if brand_profile.get("notes"):
            assumptions.append(
                f"Brand strategy notes: {brand_profile['notes'][:200]}"
            )

        # From KB — top themes
        if kb_excerpts:
            top_sources = set()
            for ex in kb_excerpts[:5]:
                if ex.get("source"):
                    top_sources.add(ex["source"])
            if top_sources:
                assumptions.append(
                    f"Knowledge base sources: {', '.join(sorted(top_sources))}"
                )

        return assumptions

    def _get_bridge(self):
        if self._ingest_bridge is None:
            try:
                from sovereign_swarm.integration.ingest_bridge import SovereignIngestBridge
                self._ingest_bridge = SovereignIngestBridge()
            except Exception:
                self._ingest_bridge = False
        return self._ingest_bridge if self._ingest_bridge is not False else None
