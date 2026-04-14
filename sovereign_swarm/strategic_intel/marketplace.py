"""MarketplaceSensor — scans Amazon, Walmart, and Google Shopping for
competitive intelligence on product businesses.

Uses SerpAPI (Google Shopping) as the primary cross-marketplace scanner,
with optional Keepa (Amazon BSR history) and Rainforest (live Amazon detail)
integration when API keys are available.

Tenant-aware: only fires for product businesses (atx_mats, gli).
Service businesses (sovereign, gbb) skip marketplace scanning.
"""

from __future__ import annotations

import asyncio
import json
import re
import structlog
from datetime import datetime
from typing import Any
from urllib.parse import quote_plus

from sovereign_swarm.strategic_intel.models import ExternalSignal

logger = structlog.get_logger()

_RATE_LIMIT = 0.5  # seconds between API calls

# Tenants that sell physical products on marketplaces
MARKETPLACE_TENANTS: dict[str, dict[str, Any]] = {
    "atx_mats": {
        "search_terms": [
            "anti fatigue mat commercial",
            "industrial floor mat",
            "anti fatigue kitchen mat",
            "commercial rubber flooring",
            "standing desk mat",
            "workshop floor mat",
            "garage floor mat heavy duty",
        ],
        "categories": ["Industrial & Scientific", "Home & Kitchen", "Sports & Outdoors"],
        "platforms": ["amazon", "walmart", "google_shopping"],
    },
    "gli": {
        "search_terms": [
            "LED strip lights",
            "LED panel light commercial",
            "LED grow light",
            "smart LED bulb",
            "LED flood light outdoor",
            "LED shop light",
            "LED under cabinet light",
        ],
        "categories": ["Tools & Home Improvement", "Lighting", "Garden & Outdoor"],
        "platforms": ["amazon", "walmart", "google_shopping"],
    },
}


class MarketplaceSensor:
    """Scans e-commerce marketplaces for competitive intelligence."""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._config = config or {}
        self._http_client = None
        self._anthropic = None

    def is_marketplace_tenant(self, tenant: str) -> bool:
        """Check if this tenant has marketplace products to scan."""
        return tenant in MARKETPLACE_TENANTS

    async def scan(self, tenant: str) -> list[ExternalSignal]:
        """Run marketplace scan for a tenant. Returns ExternalSignals."""
        if not self.is_marketplace_tenant(tenant):
            return []

        tenant_config = MARKETPLACE_TENANTS[tenant]
        all_signals: list[ExternalSignal] = []

        for term in tenant_config["search_terms"]:
            # Google Shopping gives cross-marketplace view
            signals = await self._scan_google_shopping(term, tenant)
            all_signals.extend(signals)
            await asyncio.sleep(_RATE_LIMIT)

            if len(all_signals) >= 30:  # budget cap
                break

        logger.info(
            "marketplace.scan_complete",
            tenant=tenant,
            signals=len(all_signals),
            terms_searched=len(tenant_config["search_terms"]),
        )
        return all_signals

    async def _scan_google_shopping(
        self, query: str, tenant: str
    ) -> list[ExternalSignal]:
        """Scan Google Shopping for product listings and pricing."""
        # Try SerpAPI first if key available
        serpapi_key = self._config.get("serpapi_key", "")
        if serpapi_key:
            return await self._serpapi_shopping(query, serpapi_key, tenant)

        # Fallback: LLM knowledge about marketplace landscape
        return await self._llm_marketplace_intel(query, tenant)

    async def _serpapi_shopping(
        self, query: str, api_key: str, tenant: str
    ) -> list[ExternalSignal]:
        """Query SerpAPI Google Shopping endpoint."""
        client = self._get_client()
        url = (
            f"https://serpapi.com/search.json?"
            f"engine=google_shopping&q={quote_plus(query)}"
            f"&api_key={api_key}&num=10"
        )

        try:
            resp = await client.get(url, timeout=15.0)
            resp.raise_for_status()
            data = resp.json()

            signals = []
            shopping_results = data.get("shopping_results", [])

            # Extract competitive intelligence from results
            facts = []
            prices = []
            sellers = set()
            for item in shopping_results[:10]:
                price = item.get("extracted_price", 0)
                title = item.get("title", "")
                source = item.get("source", "")
                rating = item.get("rating", "")
                reviews = item.get("reviews", 0)

                if price:
                    prices.append(price)
                if source:
                    sellers.add(source)

                fact = f"{title} — ${price}" if price else title
                if rating:
                    fact += f" ({rating}*, {reviews} reviews)"
                if source:
                    fact += f" via {source}"
                facts.append(fact)

            # Build summary facts
            summary_facts = facts[:5]
            if prices:
                summary_facts.append(
                    f"Price range for '{query}': "
                    f"${min(prices):.2f} - ${max(prices):.2f} "
                    f"(avg ${sum(prices)/len(prices):.2f})"
                )
            if sellers:
                summary_facts.append(
                    f"Top sellers: {', '.join(list(sellers)[:5])}"
                )

            signals.append(ExternalSignal(
                source_url=f"serpapi:google_shopping:{quote_plus(query)}",
                source_type="marketplace_scan",
                query_used=query,
                raw_content=json.dumps(shopping_results[:5], default=str)[:2000],
                extracted_facts=summary_facts,
                fetched_at=datetime.utcnow(),
                relevance_score=0.85,
            ))

            return signals
        except Exception as exc:
            logger.debug("marketplace.serpapi_failed", query=query, error=str(exc))
            return await self._llm_marketplace_intel(query, tenant)

    async def _scan_amazon_keepa(
        self, asin: str, api_key: str
    ) -> dict[str, Any]:
        """Query Keepa API for Amazon BSR history + price trends.

        Keepa returns historical data for:
        - Price history (new, used, Amazon)
        - BSR history
        - Review count history
        - Buy box stats
        """
        client = self._get_client()
        url = (
            f"https://api.keepa.com/product?"
            f"key={api_key}&domain=1&asin={asin}&history=1&stats=180"
        )
        try:
            resp = await client.get(url, timeout=15.0)
            resp.raise_for_status()
            data = resp.json()
            products = data.get("products", [])
            if products:
                p = products[0]
                return {
                    "asin": asin,
                    "title": p.get("title", ""),
                    "bsr": p.get("salesRanks", {}),
                    "stats": p.get("stats", {}),
                    "category": p.get("categoryTree", []),
                }
            return {}
        except Exception as exc:
            logger.debug("marketplace.keepa_failed", asin=asin, error=str(exc))
            return {}

    async def _scan_walmart(
        self, query: str, consumer_id: str
    ) -> list[ExternalSignal]:
        """Query Walmart Product API."""
        client = self._get_client()
        url = (
            f"https://developer.api.walmart.com/api-proxy/service/"
            f"affil/product/v2/search?query={quote_plus(query)}&numItems=10"
        )
        headers = {
            "WM_CONSUMER.ID": consumer_id,
            "WM_SEC.AUTH_SIGNATURE": "",  # requires crypto signing
            "Accept": "application/json",
        }
        try:
            resp = await client.get(url, headers=headers, timeout=15.0)
            resp.raise_for_status()
            data = resp.json()
            items = data.get("items", [])

            facts = []
            for item in items[:5]:
                name = item.get("name", "")
                price = item.get("salePrice", "")
                rating = item.get("customerRating", "")
                reviews = item.get("numReviews", 0)
                facts.append(
                    f"[Walmart] {name} — ${price} ({rating}*, {reviews} reviews)"
                )

            if facts:
                return [ExternalSignal(
                    source_url=f"walmart:search:{quote_plus(query)}",
                    source_type="marketplace_scan",
                    query_used=query,
                    raw_content=json.dumps(items[:3], default=str)[:2000],
                    extracted_facts=facts,
                    fetched_at=datetime.utcnow(),
                    relevance_score=0.8,
                )]
            return []
        except Exception as exc:
            logger.debug("marketplace.walmart_failed", query=query, error=str(exc))
            return []

    async def _llm_marketplace_intel(
        self, query: str, tenant: str
    ) -> list[ExternalSignal]:
        """Fallback: use LLM knowledge for marketplace intelligence."""
        client = self._get_anthropic()
        if not client:
            return []

        prompt = (
            f"You are an e-commerce market analyst. For the product search "
            f"'{query}', provide competitive intelligence:\n\n"
            f"1. Price range on Amazon and Walmart for this category\n"
            f"2. Top 3 competing brands/sellers\n"
            f"3. Common customer complaints from reviews\n"
            f"4. Any product gaps or underserved niches\n"
            f"5. Best-seller characteristics (what makes top products sell)\n\n"
            f"Return as a JSON array of factual strings. Include specific "
            f"prices, brand names, and review themes where possible.\n"
            f"Flag uncertain data with '(estimated)' suffix."
        )

        try:
            from sovereign_swarm.config import get_settings
            settings = get_settings()
            resp = await client.messages.create(
                model=settings.fast_model,
                max_tokens=500,
                messages=[{"role": "user", "content": prompt}],
            )
            text = resp.content[0].text.strip()
            if text.startswith("```"):
                text = re.sub(r"^```\w*\n?", "", text)
                text = re.sub(r"\n?```$", "", text)
            try:
                facts = json.loads(text)
            except json.JSONDecodeError:
                match = re.search(r'\[.*?\]', text, re.DOTALL)
                facts = json.loads(match.group()) if match else []

            if facts:
                return [ExternalSignal(
                    source_url="llm_knowledge:marketplace",
                    source_type="marketplace_llm",
                    query_used=query,
                    raw_content=f"LLM marketplace analysis for: {query}",
                    extracted_facts=facts,
                    fetched_at=datetime.utcnow(),
                    relevance_score=0.5,
                )]
            return []
        except Exception as exc:
            logger.debug("marketplace.llm_failed", query=query, error=str(exc))
            return []

    def _get_client(self):
        if self._http_client is None:
            import httpx
            self._http_client = httpx.AsyncClient(
                timeout=15.0,
                follow_redirects=True,
            )
        return self._http_client

    def _get_anthropic(self):
        if self._anthropic is None:
            try:
                import anthropic
                self._anthropic = anthropic.AsyncAnthropic()
            except Exception:
                self._anthropic = False
        return self._anthropic if self._anthropic is not False else None
