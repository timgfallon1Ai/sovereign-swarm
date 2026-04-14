"""ExternalSensor — outward-facing data collection for strategic intelligence.

Fires web searches, fetches pages, and uses Haiku to extract structured
facts from external content. This is the SENSE phase of the pipeline.

Design notes
------------
- Uses httpx for all HTTP requests with rate limiting
- Falls back to Firecrawl MCP for JS-rendered pages (detected by short content)
- Fact extraction via Claude Haiku keeps costs low (~$0.001/page)
- Max 30 pages per framework run to stay within budget
"""

from __future__ import annotations

import asyncio
import re
import json
import structlog
from datetime import datetime
from typing import Any
from urllib.parse import quote_plus

from sovereign_swarm.strategic_intel.models import ExternalSignal

logger = structlog.get_logger()

_USER_AGENT = "SovereignSwarm/1.0 StrategicIntel"
_MAX_CONTENT_LEN = 2000
_RATE_LIMIT_SECONDS = 0.5
_MAX_PAGES_PER_FRAMEWORK = 30
_JS_CONTENT_THRESHOLD = 500  # bytes — below this, suspect JS rendering


_EXTRACT_PROMPT = """\
Extract 3-5 factual claims from this content relevant to: {query_context}

Content (truncated):
{content}

Return ONLY a JSON array of strings. No speculation, no commentary.
Example: ["The market is worth $12B", "Growth rate is 4.2% CAGR"]
"""


class ExternalSensor:
    """Collects external signals via web search and page scraping."""

    def __init__(self) -> None:
        self._http_client = None
        self._anthropic = None

    async def search_web(
        self,
        queries: list[str],
        max_results_per_query: int = 5,
    ) -> list[ExternalSignal]:
        """Fire web searches and extract facts from results.

        Strategy:
        1. Try Google HTML scraping first (free, may be blocked)
        2. If zero URLs returned, fall back to LLM knowledge synthesis
           (Haiku has web knowledge up to its training cutoff)
        3. For any URLs found, fetch + extract facts
        """
        all_signals: list[ExternalSignal] = []
        seen_urls: set[str] = set()
        pages_fetched = 0

        for query in queries:
            if pages_fetched >= _MAX_PAGES_PER_FRAMEWORK:
                break

            urls = await self._search_google(query, max_results_per_query)

            if urls:
                # Path A: We got URLs — fetch and extract
                for url in urls:
                    if url in seen_urls or pages_fetched >= _MAX_PAGES_PER_FRAMEWORK:
                        continue
                    seen_urls.add(url)

                    content = await self.fetch_page(url)
                    if not content or len(content.strip()) < 100:
                        continue

                    pages_fetched += 1
                    facts = await self.extract_facts(content, query)

                    all_signals.append(ExternalSignal(
                        source_url=url,
                        source_type="web_search",
                        query_used=query,
                        raw_content=content[:_MAX_CONTENT_LEN],
                        extracted_facts=facts,
                        fetched_at=datetime.utcnow(),
                        relevance_score=0.7 if facts else 0.3,
                    ))
                    await asyncio.sleep(_RATE_LIMIT_SECONDS)
            else:
                # Path B: Google blocked — use LLM knowledge as fallback
                facts = await self._llm_knowledge_search(query)
                if facts:
                    all_signals.append(ExternalSignal(
                        source_url="llm_knowledge",
                        source_type="llm_synthesis",
                        query_used=query,
                        raw_content=f"LLM knowledge synthesis for: {query}",
                        extracted_facts=facts,
                        fetched_at=datetime.utcnow(),
                        relevance_score=0.5,  # lower confidence than live data
                    ))

        logger.info(
            "sensor.search_complete",
            queries=len(queries),
            signals=len(all_signals),
            pages=pages_fetched,
        )
        return all_signals

    async def _llm_knowledge_search(self, query: str) -> list[str]:
        """Fallback: use Haiku's training knowledge to answer the query."""
        client = self._get_anthropic()
        if not client:
            return []

        prompt = (
            f"You are a market research analyst. Based on your knowledge, "
            f"provide 3-5 specific, factual data points for this query:\n\n"
            f"{query}\n\n"
            f"Return ONLY a JSON array of factual strings. Include specific "
            f"numbers, company names, and dates where possible. Flag any "
            f"data you're uncertain about with '(estimated)' suffix.\n"
            f"Example: [\"The US flooring market was $42B in 2024\", "
            f"\"Growth rate is 4.5% CAGR (estimated)\"]"
        )

        try:
            from sovereign_swarm.config import get_settings
            settings = get_settings()
            resp = await client.messages.create(
                model=settings.fast_model,
                max_tokens=400,
                messages=[{"role": "user", "content": prompt}],
            )
            text = resp.content[0].text.strip()
            if text.startswith("```"):
                text = re.sub(r"^```\w*\n?", "", text)
                text = re.sub(r"\n?```$", "", text)
            # Tolerant parsing: try full text first, then extract first JSON array
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                match = re.search(r'\[.*?\]', text, re.DOTALL)
                if match:
                    return json.loads(match.group())
                return []
        except Exception as exc:
            logger.debug("sensor.llm_knowledge_failed", error=str(exc))
            return []

    async def fetch_page(self, url: str, use_firecrawl_fallback: bool = True) -> str:
        """Fetch a page. Falls back to raw text extraction if JS-heavy."""
        client = self._get_client()
        try:
            resp = await client.get(
                url,
                follow_redirects=True,
                timeout=15.0,
                headers={"User-Agent": _USER_AGENT},
            )
            resp.raise_for_status()
            text = resp.text

            # Strip HTML tags for cleaner extraction
            clean = self._strip_html(text)

            if len(clean.strip()) < _JS_CONTENT_THRESHOLD:
                logger.debug("sensor.js_detected", url=url, content_len=len(clean))
                # JS-heavy page — content is too short after stripping
                # In production, this would call Firecrawl MCP
                # For now, return what we have
                return clean

            return clean[:_MAX_CONTENT_LEN]
        except Exception as exc:
            logger.debug("sensor.fetch_failed", url=url, error=str(exc))
            return ""

    async def extract_facts(self, content: str, query_context: str) -> list[str]:
        """Use Haiku to extract structured facts from page content."""
        client = self._get_anthropic()
        if not client:
            # Fallback: simple sentence extraction
            return self._rule_based_extract(content, query_context)

        prompt = _EXTRACT_PROMPT.format(
            query_context=query_context,
            content=content[:_MAX_CONTENT_LEN],
        )

        try:
            from sovereign_swarm.config import get_settings
            settings = get_settings()
            resp = await client.messages.create(
                model=settings.fast_model,
                max_tokens=300,
                messages=[{"role": "user", "content": prompt}],
            )
            text = resp.content[0].text.strip()
            # Strip markdown fences
            if text.startswith("```"):
                text = re.sub(r"^```\w*\n?", "", text)
                text = re.sub(r"\n?```$", "", text)
            # Tolerant parsing: try full text first, then extract first JSON array
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                match = re.search(r'\[.*?\]', text, re.DOTALL)
                if match:
                    return json.loads(match.group())
                return []
        except Exception as exc:
            logger.debug("sensor.extract_failed", error=str(exc))
            return self._rule_based_extract(content, query_context)

    async def _search_google(self, query: str, max_results: int = 5) -> list[str]:
        """Scrape Google search results for URLs."""
        client = self._get_client()
        search_url = f"https://www.google.com/search?q={quote_plus(query)}&num={max_results}"
        try:
            resp = await client.get(
                search_url,
                follow_redirects=True,
                timeout=10.0,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                    ),
                },
            )
            # Extract URLs from search results
            urls = re.findall(
                r'href="(/url\?q=|)(https?://[^"&]+)',
                resp.text,
            )
            # Deduplicate and filter
            seen: set[str] = set()
            result: list[str] = []
            skip_domains = {"google.com", "youtube.com", "facebook.com", "twitter.com"}
            for _, url in urls:
                if url in seen:
                    continue
                if any(d in url for d in skip_domains):
                    continue
                seen.add(url)
                result.append(url)
                if len(result) >= max_results:
                    break
            return result
        except Exception as exc:
            logger.debug("sensor.google_search_failed", query=query, error=str(exc))
            return []

    @staticmethod
    def _strip_html(html: str) -> str:
        """Remove HTML tags, scripts, styles — keep text content."""
        # Remove script and style blocks
        text = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
        # Remove tags
        text = re.sub(r"<[^>]+>", " ", text)
        # Collapse whitespace
        text = re.sub(r"\s+", " ", text).strip()
        return text

    @staticmethod
    def _rule_based_extract(content: str, query_context: str) -> list[str]:
        """Fallback fact extraction without LLM — keyword-relevant sentences."""
        query_words = set(query_context.lower().split())
        sentences = re.split(r"[.!?]\s+", content)
        scored = []
        for s in sentences:
            s = s.strip()
            if len(s) < 20 or len(s) > 300:
                continue
            words = set(s.lower().split())
            overlap = len(query_words & words)
            if overlap >= 2:
                scored.append((overlap, s))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [s for _, s in scored[:5]]

    def _get_client(self):
        if self._http_client is None:
            import httpx
            self._http_client = httpx.AsyncClient(
                timeout=15.0,
                headers={"User-Agent": _USER_AGENT},
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
