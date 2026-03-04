"""
Elfa AI Client — sentiment analysis, trending tokens, keyword mentions.

API: https://api.elfa.ai/v2/
Auth: x-elfa-api-key header
Rate limit: 100 requests/minute

Endpoints used:
- GET /v2/aggregations/trending-tokens   — trending by mention count
- GET /v2/aggregations/trending-narratives — trending narratives (5 credits)
- GET /v2/data/top-mentions              — top mentions for a ticker
- GET /v2/data/keyword-mentions          — search by keywords
- GET /v2/data/token-news                — token-related news
- GET /v2/key-status                     — check API key status
"""
import aiohttp
import structlog
from typing import Any

from src.core.cache import Cache, CACHE_TTL

log = structlog.get_logger()

BASE_URL = "https://api.elfa.ai/v2"


class ElfaClient:
    """Async client for Elfa AI REST API v2."""

    def __init__(self, api_key: str, cache: Cache):
        self.api_key = api_key
        self.cache = cache
        self._session: aiohttp.ClientSession | None = None

    async def _ensure_session(self):
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                headers={"x-elfa-api-key": self.api_key},
                timeout=aiohttp.ClientTimeout(total=30),
            )

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    async def _get(self, endpoint: str, params: dict | None = None) -> dict | None:
        """Make a GET request to Elfa API."""
        await self._ensure_session()
        url = f"{BASE_URL}/{endpoint}"
        try:
            async with self._session.get(url, params=params) as resp:
                if resp.status == 429:
                    retry_after = int(resp.headers.get("Retry-After", 60))
                    log.warning("elfa.rate_limited", retry_after=retry_after)
                    return None
                if resp.status == 401:
                    log.error("elfa.auth_failed")
                    return None
                resp.raise_for_status()
                return await resp.json()
        except Exception as e:
            log.error("elfa.request_failed", endpoint=endpoint, error=str(e))
            return None

    # ── Trending & Discovery ────────────────────────────────

    async def get_trending_tokens(
        self, time_window: str = "24h", page_size: int = 20
    ) -> dict | None:
        """Get tokens trending by mention count."""
        cache_key = f"elfa:trending_tokens:{time_window}"
        return await self.cache.get_or_fetch(
            cache_key,
            lambda: self._get(
                "aggregations/trending-tokens",
                {"timeWindow": time_window, "pageSize": page_size},
            ),
            ttl=CACHE_TTL["elfa:trending_tokens"],
        )

    async def get_trending_narratives(self) -> dict | None:
        """Get trending narratives from Twitter analysis. Costs 5 credits."""
        cache_key = "elfa:trending_narratives"
        return await self.cache.get_or_fetch(
            cache_key,
            lambda: self._get("aggregations/trending-narratives"),
            ttl=CACHE_TTL["elfa:trending_narratives"],
        )

    async def get_trending_contract_addresses(
        self, platform: str = "twitter", time_window: str = "24h"
    ) -> dict | None:
        """Get trending contract addresses on Twitter or Telegram."""
        cache_key = f"elfa:trending_cas:{platform}:{time_window}"
        return await self.cache.get_or_fetch(
            cache_key,
            lambda: self._get(
                f"aggregations/trending-cas/{platform}",
                {"timeWindow": time_window},
            ),
            ttl=300,
        )

    # ── Mentions & Sentiment ────────────────────────────────

    async def get_top_mentions(
        self, ticker: str, time_window: str = "1h"
    ) -> dict | None:
        """Get top mentions for a specific ticker (e.g., 'bitcoin')."""
        cache_key = f"elfa:top_mentions:{ticker}:{time_window}"
        return await self.cache.get_or_fetch(
            cache_key,
            lambda: self._get(
                "data/top-mentions",
                {"ticker": ticker, "timeWindow": time_window},
            ),
            ttl=CACHE_TTL["elfa:top_mentions"],
        )

    async def search_mentions(
        self,
        keywords: str,
        from_ts: int | None = None,
        to_ts: int | None = None,
        limit: int = 20,
    ) -> dict | None:
        """Search mentions by keywords with optional time range."""
        params: dict[str, Any] = {"keywords": keywords, "limit": limit}
        if from_ts:
            params["from"] = from_ts
        if to_ts:
            params["to"] = to_ts

        cache_key = f"elfa:keyword_mentions:{keywords}:{from_ts}:{to_ts}"
        return await self.cache.get_or_fetch(
            cache_key,
            lambda: self._get("data/keyword-mentions", params),
            ttl=CACHE_TTL["elfa:keyword_mentions"],
        )

    # ── News ────────────────────────────────────────────────

    async def get_token_news(self, ticker: str) -> dict | None:
        """Get news mentions for a token."""
        cache_key = f"elfa:token_news:{ticker}"
        return await self.cache.get_or_fetch(
            cache_key,
            lambda: self._get("data/token-news", {"ticker": ticker}),
            ttl=CACHE_TTL["elfa:token_news"],
        )

    # ── Utility ─────────────────────────────────────────────

    async def check_key_status(self) -> dict | None:
        """Check API key status and remaining credits."""
        return await self._get("key-status")
