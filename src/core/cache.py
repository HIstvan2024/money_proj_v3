"""
Cache — Redis-backed caching layer for API responses.
Reduces API calls, respects rate limits, and keeps agents fast.

Usage:
    cache = Cache(bus)
    
    # Cache with TTL
    data = await cache.get_or_fetch("elfa:trending:24h", fetch_fn, ttl=300)
    
    # Manual cache
    await cache.set("price:BTC", price_data, ttl=60)
    data = await cache.get("price:BTC")
    
    # Invalidate
    await cache.invalidate("elfa:trending:*")
"""
import time
import orjson
import structlog
from typing import Any, Callable, Awaitable

from src.core.bus import MessageBus

log = structlog.get_logger()


class Cache:
    """Redis-backed cache with TTL, namespacing, and cache-aside pattern."""

    PREFIX = "cache:"

    def __init__(self, bus: MessageBus):
        self.bus = bus
        self._stats = {"hits": 0, "misses": 0, "sets": 0}

    def _key(self, key: str) -> str:
        return f"{self.PREFIX}{key}"

    async def get(self, key: str) -> Any | None:
        """Get a cached value. Returns None if expired or missing."""
        raw = await self.bus.get(self._key(key))
        if raw is None:
            self._stats["misses"] += 1
            return None

        try:
            envelope = orjson.loads(raw)
            self._stats["hits"] += 1
            log.debug("cache.hit", key=key)
            return envelope["data"]
        except (orjson.JSONDecodeError, KeyError):
            self._stats["misses"] += 1
            return None

    async def set(self, key: str, data: Any, ttl: int = 300) -> None:
        """Cache a value with TTL (default 5 minutes)."""
        envelope = {
            "data": data,
            "cached_at": time.time(),
            "ttl": ttl,
        }
        await self.bus.set(self._key(key), orjson.dumps(envelope), ttl=ttl)
        self._stats["sets"] += 1
        log.debug("cache.set", key=key, ttl=ttl)

    async def get_or_fetch(
        self,
        key: str,
        fetch_fn: Callable[[], Awaitable[Any]],
        ttl: int = 300,
    ) -> Any:
        """Cache-aside pattern: return cached data or fetch and cache."""
        cached = await self.get(key)
        if cached is not None:
            return cached

        # Cache miss — fetch fresh data
        data = await fetch_fn()
        if data is not None:
            await self.set(key, data, ttl=ttl)
        return data

    async def invalidate(self, key: str) -> None:
        """Delete a specific cache key."""
        redis = self.bus._redis
        await redis.delete(self._key(key))
        log.debug("cache.invalidated", key=key)

    async def invalidate_prefix(self, prefix: str) -> None:
        """Invalidate all keys matching a prefix (use sparingly)."""
        redis = self.bus._redis
        pattern = f"{self.PREFIX}{prefix}*"
        cursor = 0
        deleted = 0
        while True:
            cursor, keys = await redis.scan(cursor, match=pattern, count=100)
            if keys:
                await redis.delete(*keys)
                deleted += len(keys)
            if cursor == 0:
                break
        log.info("cache.prefix_invalidated", prefix=prefix, deleted=deleted)

    def stats(self) -> dict:
        total = self._stats["hits"] + self._stats["misses"]
        hit_rate = (self._stats["hits"] / total * 100) if total > 0 else 0
        return {**self._stats, "hit_rate": f"{hit_rate:.1f}%"}


# ── Recommended TTLs ───────────────────────────────────────
# These balance freshness vs. rate limits.

CACHE_TTL = {
    # Elfa AI (100 req/min limit)
    "elfa:trending_tokens": 300,       # 5 min — trending doesn't change fast
    "elfa:top_mentions": 180,          # 3 min
    "elfa:keyword_mentions": 120,      # 2 min — more time-sensitive
    "elfa:trending_narratives": 600,   # 10 min — narratives shift slowly
    "elfa:token_news": 300,            # 5 min

    # Polymarket
    "poly:markets": 120,               # 2 min — market list
    "poly:positions": 60,              # 1 min — own positions (more critical)
    "poly:orderbook": 30,              # 30 sec — order book changes fast

    # Grok / xAI
    "grok:sentiment": 180,             # 3 min — sentiment analysis
    "grok:research": 300,              # 5 min — deeper research

    # Price data (Binance WS fills real-time, this is for REST fallback)
    "price:kline": 60,                 # 1 min
    "price:ticker": 15,                # 15 sec
}
