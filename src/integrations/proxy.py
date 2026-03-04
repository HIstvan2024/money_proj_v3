"""
Proxy Manager — IPRoyal residential proxy with country rotation.

Polymarket sometimes rejects a proxy from the same country twice.
This manager auto-rotates through countries on failure.

Input format (from env):
    HOST:PORT:USER:PASS

IPRoyal country targeting:
    Append _country-XX to the username to force a specific country.
    e.g., user123_country-br → Brazil
          user123_country-ca → Canada
          user123_country-de → Germany
    Without suffix → random country (residential pool)

Usage:
    proxy = ProxyManager(host, port, user, password)
    
    # Get a proxy URL (tries random first, then rotates countries)
    url = proxy.get_proxy_url()
    
    # Mark current proxy as failed → rotates to next country
    proxy.mark_failed()
    
    # Use in aiohttp:
    async with session.get(url, proxy=proxy.get_proxy_url()) as resp:
        ...
"""
import random
import time
import structlog
from dataclasses import dataclass, field

log = structlog.get_logger()

# Countries that generally work well with Polymarket
# Ordered by reliability — adjust based on your experience
COUNTRY_POOL = [
    "",     # No suffix = random country (try first)
    "us",   # United States
    "ca",   # Canada
    "gb",   # United Kingdom
    "de",   # Germany
    "fr",   # France
    "nl",   # Netherlands
    "br",   # Brazil
    "au",   # Australia
    "jp",   # Japan
    "sg",   # Singapore
    "kr",   # South Korea
    "in",   # India
    "mx",   # Mexico
    "ar",   # Argentina
    "it",   # Italy
    "es",   # Spain
    "se",   # Sweden
    "ch",   # Switzerland
    "pl",   # Poland
]


@dataclass
class ProxyAttempt:
    country: str
    timestamp: float
    success: bool


@dataclass
class ProxyManager:
    """Manages IPRoyal residential proxy with country rotation."""

    host: str
    port: str
    user: str
    password: str
    max_retries: int = 5
    cooldown_seconds: int = 300  # 5 min cooldown for failed countries

    _current_index: int = field(default=0, init=False)
    _failed_countries: dict = field(default_factory=dict, init=False)  # country -> fail_timestamp
    _history: list = field(default_factory=list, init=False)
    _last_success_country: str = field(default="", init=False)

    @classmethod
    def from_env(cls, proxy_string: str, max_retries: int = 5) -> "ProxyManager":
        """
        Parse from HOST:PORT:USER:PASS format.

        Example: geo.iproyal.com:12321:user123:pass456
        """
        parts = proxy_string.strip().split(":")
        if len(parts) != 4:
            raise ValueError(
                f"Expected HOST:PORT:USER:PASS format, got {len(parts)} parts. "
                f"Input: {proxy_string[:20]}..."
            )
        return cls(
            host=parts[0],
            port=parts[1],
            user=parts[2],
            password=parts[3],
            max_retries=max_retries,
        )

    def _get_username(self, country: str = "") -> str:
        """Build username with optional country suffix."""
        if country:
            return f"{self.user}_country-{country}"
        return self.user

    def _is_country_cooled_down(self, country: str) -> bool:
        """Check if a failed country is still in cooldown."""
        if country not in self._failed_countries:
            return False
        elapsed = time.time() - self._failed_countries[country]
        return elapsed < self.cooldown_seconds

    def _get_available_countries(self) -> list[str]:
        """Get countries not currently in cooldown."""
        return [c for c in COUNTRY_POOL if not self._is_country_cooled_down(c)]

    def get_current_country(self) -> str:
        """Get the current country being used."""
        available = self._get_available_countries()
        if not available:
            # All countries exhausted — clear cooldowns and start over
            log.warning("proxy.all_countries_exhausted, resetting cooldowns")
            self._failed_countries.clear()
            available = COUNTRY_POOL.copy()

        if self._current_index >= len(available):
            self._current_index = 0

        return available[self._current_index]

    def get_proxy_url(self) -> str:
        """
        Get the current proxy URL in http://user:pass@host:port format.
        Ready to use in aiohttp/requests.
        """
        country = self.get_current_country()
        username = self._get_username(country)
        url = f"http://{username}:{self.password}@{self.host}:{self.port}"

        country_label = country if country else "random"
        log.debug("proxy.using", country=country_label, host=self.host)
        return url

    def get_proxy_dict(self) -> dict:
        """Get proxy config as dict (for libraries that need it)."""
        url = self.get_proxy_url()
        return {"http": url, "https": url}

    def mark_failed(self, reason: str = ""):
        """
        Mark current country as failed. Moves to next country.
        Called by the execution agent when Polymarket rejects the proxy.
        """
        country = self.get_current_country()
        country_label = country if country else "random"

        self._failed_countries[country] = time.time()
        self._history.append(ProxyAttempt(
            country=country_label,
            timestamp=time.time(),
            success=False,
        ))

        log.warning(
            "proxy.country_failed",
            country=country_label,
            reason=reason,
            cooldown=self.cooldown_seconds,
        )

        # Move to next country
        self._current_index += 1

    def mark_success(self):
        """Mark current country as successful. Remember it."""
        country = self.get_current_country()
        country_label = country if country else "random"
        self._last_success_country = country

        # Remove from failed list if it was there
        self._failed_countries.pop(country, None)

        self._history.append(ProxyAttempt(
            country=country_label,
            timestamp=time.time(),
            success=True,
        ))

        log.info("proxy.country_success", country=country_label)

    def shuffle_countries(self):
        """Randomize country order (useful for fresh start)."""
        pool = COUNTRY_POOL.copy()
        random.shuffle(pool)
        # Keep "" (random) as first option
        if "" in pool:
            pool.remove("")
            pool.insert(0, "")
        log.info("proxy.countries_shuffled")

    def stats(self) -> dict:
        """Get proxy usage statistics."""
        recent = self._history[-20:] if self._history else []
        successes = sum(1 for a in recent if a.success)
        failures = sum(1 for a in recent if not a.success)
        available = len(self._get_available_countries())
        cooled = len(self._failed_countries)

        return {
            "current_country": self.get_current_country() or "random",
            "last_success": self._last_success_country or "none",
            "available_countries": available,
            "cooled_down_countries": cooled,
            "recent_successes": successes,
            "recent_failures": failures,
        }


async def execute_with_proxy_rotation(
    proxy_manager: ProxyManager,
    execute_fn,
    max_retries: int | None = None,
):
    """
    Execute a function with automatic proxy country rotation on failure.

    Usage:
        result = await execute_with_proxy_rotation(
            proxy_manager,
            lambda proxy_url: place_order(proxy_url, order_data),
        )

    The execute_fn receives the proxy URL and should raise on proxy rejection.
    """
    retries = max_retries or proxy_manager.max_retries

    for attempt in range(retries):
        proxy_url = proxy_manager.get_proxy_url()
        country = proxy_manager.get_current_country() or "random"

        try:
            log.info(
                "proxy.attempt",
                attempt=attempt + 1,
                max_retries=retries,
                country=country,
            )
            result = await execute_fn(proxy_url)
            proxy_manager.mark_success()
            return result

        except Exception as e:
            error_str = str(e).lower()

            # Detect proxy-specific failures
            is_proxy_error = any(hint in error_str for hint in [
                "proxy",
                "403",
                "forbidden",
                "blocked",
                "geo",
                "region",
                "access denied",
                "connection refused",
                "timeout",
                "too many requests",
                "rate limit",
            ])

            if is_proxy_error:
                proxy_manager.mark_failed(reason=str(e)[:100])
                log.warning(
                    "proxy.rotation",
                    failed_country=country,
                    attempt=attempt + 1,
                    next_country=proxy_manager.get_current_country() or "random",
                )
            else:
                # Not a proxy error — don't rotate, just raise
                log.error("proxy.non_proxy_error", error=str(e))
                raise

    # All retries exhausted
    raise RuntimeError(
        f"All {retries} proxy attempts failed. "
        f"Stats: {proxy_manager.stats()}"
    )
