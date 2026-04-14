"""Apollo.io client for prospect discovery.

Reads APOLLO_API_KEY from environment. Rate-limited to 50 req/min.
Search produces Contact + Company records ready for store.upsert.
"""

from __future__ import annotations

import asyncio
import os
from datetime import datetime
from typing import Any

import structlog

from sovereign_swarm.sales_ops.models import (
    Company,
    Contact,
    ContactSource,
)

logger = structlog.get_logger()

_APOLLO_BASE = "https://api.apollo.io/api/v1"
_RATE_LIMIT_DELAY = 1.3  # ~46 req/min, safe under 50/min ceiling


class ApolloClient:
    """Thin wrapper around Apollo.io REST API."""

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or os.getenv("APOLLO_API_KEY", "")
        self._http = None
        self._last_request_at: float = 0.0

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key)

    async def close(self) -> None:
        if self._http is not None:
            await self._http.aclose()
            self._http = None

    async def _client(self):
        if self._http is None:
            import httpx
            self._http = httpx.AsyncClient(
                timeout=30.0,
                headers={
                    "X-Api-Key": self.api_key,
                    "Cache-Control": "no-cache",
                    "Content-Type": "application/json",
                },
            )
        return self._http

    async def _rate_limit(self) -> None:
        loop = asyncio.get_event_loop()
        now = loop.time()
        elapsed = now - self._last_request_at
        if elapsed < _RATE_LIMIT_DELAY:
            await asyncio.sleep(_RATE_LIMIT_DELAY - elapsed)
        self._last_request_at = loop.time()

    async def search_people(
        self,
        tenant: str,
        titles: list[str] | None = None,
        keywords: str = "",
        industries: list[str] | None = None,
        locations: list[str] | None = None,
        company_size: list[str] | None = None,
        limit: int = 25,
    ) -> list[tuple[Contact, Company]]:
        """Search Apollo for people matching ICP.

        Returns list of (Contact, Company) tuples ready for upsert.
        """
        if not self.is_configured:
            logger.warning("apollo.not_configured")
            return []

        payload: dict[str, Any] = {
            "page": 1,
            "per_page": min(limit, 100),
        }
        if titles:
            payload["person_titles"] = titles
        if keywords:
            payload["q_keywords"] = keywords
        if industries:
            payload["organization_industry_tag_ids"] = industries
        if locations:
            payload["person_locations"] = locations
        if company_size:
            payload["organization_num_employees_ranges"] = company_size

        await self._rate_limit()
        client = await self._client()
        try:
            resp = await client.post(
                f"{_APOLLO_BASE}/mixed_people/api_search",
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            logger.error("apollo.search_failed", error=str(exc))
            return []

        # Apollo Basic returns obfuscated results by default. To get the
        # real email + full name, we must enrich each hit via people/match.
        # This costs 1 credit per reveal.
        results: list[tuple[Contact, Company]] = []
        for person in data.get("people", [])[:limit]:
            enriched = await self._enrich_by_id(person.get("id", ""), tenant)
            if enriched is None:
                # fall back to raw search result (will have redacted fields)
                enriched = self._person_to_records(person, tenant)
            contact, company = enriched
            if contact.email or contact.linkedin_url:
                results.append((contact, company))
            await asyncio.sleep(_RATE_LIMIT_DELAY)

        logger.info(
            "apollo.search_complete",
            tenant=tenant,
            requested=limit,
            returned=len(results),
        )
        return results

    async def _enrich_by_id(self, person_id: str, tenant: str) -> tuple[Contact, Company] | None:
        """Enrich a single person by Apollo ID. Costs 1 credit."""
        if not person_id:
            return None
        await self._rate_limit()
        client = await self._client()
        try:
            resp = await client.post(
                f"{_APOLLO_BASE}/people/match",
                json={"id": person_id, "reveal_personal_emails": True},
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            logger.debug("apollo.enrich_by_id_failed", person_id=person_id, error=str(exc))
            return None

        person = data.get("person")
        if not person:
            return None
        contact, company = self._person_to_records(person, tenant)
        # prefer personal emails if primary email is hidden
        if not contact.email:
            personal_emails = person.get("personal_emails") or []
            org_emails = person.get("organization_emails") or []
            if personal_emails:
                contact.email = personal_emails[0]
            elif org_emails:
                contact.email = org_emails[0]
        return contact, company

    async def enrich_contact(
        self,
        email: str = "",
        linkedin_url: str = "",
        tenant: str = "",
    ) -> tuple[Contact, Company] | None:
        """Enrich a single contact via Apollo People Enrichment API."""
        if not self.is_configured:
            return None
        if not (email or linkedin_url):
            return None

        payload: dict[str, Any] = {}
        if email:
            payload["email"] = email
        if linkedin_url:
            payload["linkedin_url"] = linkedin_url

        await self._rate_limit()
        client = await self._client()
        try:
            resp = await client.post(f"{_APOLLO_BASE}/people/match", json=payload)
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            logger.error("apollo.enrich_failed", error=str(exc))
            return None

        person = data.get("person")
        if not person:
            return None
        return self._person_to_records(person, tenant or "")

    @staticmethod
    def _person_to_records(person: dict[str, Any], tenant: str) -> tuple[Contact, Company]:
        """Convert an Apollo `person` record into (Contact, Company)."""
        org = person.get("organization") or {}

        company = Company(
            tenant=tenant,
            name=org.get("name") or "",
            domain=org.get("primary_domain") or "",
            industry=org.get("industry") or "",
            size=str(org.get("estimated_num_employees") or ""),
            region=org.get("country") or "",
            source=ContactSource.APOLLO,
        )

        contact = Contact(
            tenant=tenant,
            email=person.get("email") or "",
            phone=(person.get("phone_numbers") or [{}])[0].get("sanitized_number", "") if person.get("phone_numbers") else "",
            first_name=person.get("first_name") or "",
            last_name=person.get("last_name") or "",
            role=person.get("title") or "",
            linkedin_url=person.get("linkedin_url") or "",
            source=ContactSource.APOLLO,
            tags=["apollo_prospect"],
        )
        return contact, company
