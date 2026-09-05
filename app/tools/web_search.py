import os
from typing import Any, Dict, List
from urllib.parse import quote_plus

import httpx

from app.infrastructure.http.resilience import NonRetryableError, resilient_request


class WebSearchClient:
    """Qualitative news search with Tavily/SerpAPI when keyed, else DuckDuckGo."""

    def __init__(self, timeout: float = 5.0) -> None:
        self.timeout = timeout
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json,text/html;q=0.9,*/*;q=0.8",
        }

    async def search_company_news(
        self, ticker: str, query: str, max_results: int = 3
    ) -> List[Dict[str, str]]:
        try:
            return await resilient_request(
                "web_search",
                self._search_impl,
                ticker,
                query,
                max_results,
                timeout=self.timeout,
            )
        except (NonRetryableError, Exception):
            return []

    async def _search_impl(self, ticker: str, query: str, max_results: int) -> List[Dict[str, str]]:
        tavily_key = os.getenv("TAVILY_API_KEY")
        if tavily_key:
            return await self._search_tavily(tavily_key, ticker, query, max_results)
        serp_key = os.getenv("SERPAPI_API_KEY")
        if serp_key:
            return await self._search_serpapi(serp_key, ticker, query, max_results)
        return await self._search_duckduckgo(ticker, query, max_results)

    async def _search_tavily(
        self, api_key: str, ticker: str, query: str, max_results: int
    ) -> List[Dict[str, str]]:
        async with httpx.AsyncClient(timeout=self.timeout, headers=self.headers) as client:
            response = await client.post(
                "https://api.tavily.com/search",
                json={
                    "api_key": api_key,
                    "query": f"{ticker} {query}",
                    "max_results": max_results,
                    "topic": "news",
                },
            )
            response.raise_for_status()
            payload = response.json()
        return [
            {
                "title": str(item.get("title") or ""),
                "url": str(item.get("url") or ""),
                "snippet": str(item.get("content") or item.get("snippet") or ""),
                "published_date": str(item.get("published_date") or ""),
            }
            for item in (payload.get("results") or [])[:max_results]
        ]

    async def _search_serpapi(
        self, api_key: str, ticker: str, query: str, max_results: int
    ) -> List[Dict[str, str]]:
        async with httpx.AsyncClient(timeout=self.timeout, headers=self.headers) as client:
            response = await client.get(
                "https://serpapi.com/search.json",
                params={"engine": "google", "q": f"{ticker} {query} news", "api_key": api_key},
            )
            response.raise_for_status()
            payload = response.json()
        return [
            {
                "title": str(item.get("title") or ""),
                "url": str(item.get("link") or ""),
                "snippet": str(item.get("snippet") or ""),
                "published_date": str(item.get("date") or ""),
            }
            for item in (payload.get("news_results") or payload.get("organic_results") or [])[:max_results]
        ]

    async def _search_duckduckgo(self, ticker: str, query: str, max_results: int) -> List[Dict[str, str]]:
        q = f"{ticker} {query} earnings news"
        async with httpx.AsyncClient(
            timeout=self.timeout, headers=self.headers, follow_redirects=True
        ) as client:
            response = await client.get(
                "https://api.duckduckgo.com/",
                params={"q": q, "format": "json", "no_html": 1, "skip_disambig": 1},
            )
            response.raise_for_status()
            payload: Dict[str, Any] = response.json()

        items: List[Dict[str, str]] = []
        abstract = str(payload.get("AbstractText") or "")
        abstract_url = str(payload.get("AbstractURL") or "")
        if abstract:
            items.append(
                {
                    "title": str(payload.get("Heading") or f"{ticker} news"),
                    "url": abstract_url or f"https://duckduckgo.com/?q={quote_plus(q)}",
                    "snippet": abstract,
                    "published_date": "",
                }
            )
        for related in payload.get("RelatedTopics") or []:
            if not isinstance(related, dict):
                continue
            text = str(related.get("Text") or "")
            url = str((related.get("FirstURL") or ""))
            if not text:
                continue
            items.append(
                {
                    "title": text.split(" - ", 1)[0][:120],
                    "url": url,
                    "snippet": text,
                    "published_date": "",
                }
            )
            if len(items) >= max_results:
                break
        return items[:max_results]
