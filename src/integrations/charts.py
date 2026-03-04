"""
Binance WebSocket Client — real-time kline/candlestick data.

No API key required for public market data streams.
Docs: https://developers.binance.com/docs/binance-spot-api-docs/web-socket-streams

Streams used:
- <symbol>@kline_<interval>  — candlestick/kline updates
- <symbol>@ticker             — 24hr ticker price change
- <symbol>@trade              — individual trades (high volume)

Supported intervals: 1m, 3m, 5m, 15m, 30m, 1h, 2h, 4h, 6h, 8h, 12h, 1d, 3d, 1w, 1M
"""
import asyncio
import aiohttp
import orjson
import structlog
from datetime import datetime, timezone
from typing import Callable, Awaitable
from collections import deque

from src.core.bus import MessageBus

log = structlog.get_logger()

WS_BASE = "wss://stream.binance.com:9443/ws"
REST_BASE = "https://api.binance.com/api/v3"


class CandleData:
    """Single candlestick data point."""

    def __init__(self, raw: dict):
        k = raw.get("k", raw)
        self.symbol = k.get("s", "")
        self.interval = k.get("i", "")
        self.open_time = k.get("t", 0)
        self.close_time = k.get("T", 0)
        self.open = float(k.get("o", 0))
        self.high = float(k.get("h", 0))
        self.low = float(k.get("l", 0))
        self.close = float(k.get("c", 0))
        self.volume = float(k.get("v", 0))
        self.is_closed = k.get("x", False)

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "interval": self.interval,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
            "open_time": self.open_time,
            "close_time": self.close_time,
            "is_closed": self.is_closed,
        }


class ChartBuffer:
    """In-memory ring buffer of candles for a symbol/interval pair."""

    def __init__(self, max_candles: int = 200):
        self.candles: deque[dict] = deque(maxlen=max_candles)
        self.current: dict | None = None

    def update(self, candle: CandleData):
        if candle.is_closed:
            self.candles.append(candle.to_dict())
            self.current = None
        else:
            self.current = candle.to_dict()

    def get_history(self, count: int | None = None) -> list[dict]:
        """Get closed candles + current live candle."""
        history = list(self.candles)
        if self.current:
            history.append(self.current)
        if count:
            return history[-count:]
        return history

    def latest_price(self) -> float | None:
        if self.current:
            return self.current["close"]
        if self.candles:
            return self.candles[-1]["close"]
        return None


class BinanceChartClient:
    """Real-time crypto chart data via Binance WebSocket."""

    def __init__(self, bus: MessageBus):
        self.bus = bus
        self._ws: aiohttp.ClientWebSocketResponse | None = None
        self._session: aiohttp.ClientSession | None = None
        self._running = False
        self._subscriptions: dict[str, str] = {}  # stream_name -> symbol
        self._buffers: dict[str, ChartBuffer] = {}  # "BTCUSDT:1h" -> buffer
        self._callbacks: list[Callable[[CandleData], Awaitable[None]]] = []

    def on_candle(self, callback: Callable[[CandleData], Awaitable[None]]):
        """Register a callback for candle updates."""
        self._callbacks.append(callback)

    def _buffer_key(self, symbol: str, interval: str) -> str:
        return f"{symbol}:{interval}"

    def get_buffer(self, symbol: str, interval: str) -> ChartBuffer | None:
        return self._buffers.get(self._buffer_key(symbol, interval))

    def get_price(self, symbol: str, interval: str = "1m") -> float | None:
        buf = self.get_buffer(symbol, interval)
        return buf.latest_price() if buf else None

    async def subscribe(self, symbol: str, interval: str = "1h"):
        """Subscribe to kline stream for a symbol."""
        symbol_lower = symbol.lower()
        stream = f"{symbol_lower}@kline_{interval}"
        self._subscriptions[stream] = symbol.upper()

        key = self._buffer_key(symbol.upper(), interval)
        if key not in self._buffers:
            self._buffers[key] = ChartBuffer()

        # Load historical candles via REST
        await self._load_history(symbol.upper(), interval)

        log.info("chart.subscribed", symbol=symbol, interval=interval)

    async def _load_history(self, symbol: str, interval: str, limit: int = 100):
        """Pre-fill buffer with historical klines from REST API."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()

        url = f"{REST_BASE}/klines"
        params = {"symbol": symbol, "interval": interval, "limit": limit}

        try:
            async with self._session.get(url, params=params) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    key = self._buffer_key(symbol, interval)
                    buf = self._buffers[key]
                    for k in data:
                        candle_dict = {
                            "symbol": symbol,
                            "interval": interval,
                            "open": float(k[1]),
                            "high": float(k[2]),
                            "low": float(k[3]),
                            "close": float(k[4]),
                            "volume": float(k[5]),
                            "open_time": k[0],
                            "close_time": k[6],
                            "is_closed": True,
                        }
                        buf.candles.append(candle_dict)
                    log.info("chart.history_loaded", symbol=symbol, candles=len(data))
        except Exception as e:
            log.error("chart.history_failed", symbol=symbol, error=str(e))

    async def start(self):
        """Connect to Binance WebSocket and stream data."""
        self._running = True

        while self._running:
            try:
                await self._connect_and_stream()
            except Exception as e:
                log.error("chart.connection_error", error=str(e))
                if self._running:
                    log.info("chart.reconnecting", delay=5)
                    await asyncio.sleep(5)

    async def _connect_and_stream(self):
        """Establish WS connection and process messages."""
        if not self._subscriptions:
            log.warning("chart.no_subscriptions")
            await asyncio.sleep(10)
            return

        # Combined stream URL
        streams = "/".join(self._subscriptions.keys())
        url = f"wss://stream.binance.com:9443/stream?streams={streams}"

        self._session = aiohttp.ClientSession()
        async with self._session.ws_connect(url) as ws:
            self._ws = ws
            log.info("chart.connected", streams=len(self._subscriptions))

            async for msg in ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    await self._handle_message(msg.data)
                elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                    break

    async def _handle_message(self, raw: str):
        """Parse incoming kline message and update buffers."""
        try:
            data = orjson.loads(raw)
            # Combined stream wraps in {"stream": "...", "data": {...}}
            payload = data.get("data", data)

            if payload.get("e") != "kline":
                return

            candle = CandleData(payload)
            key = self._buffer_key(candle.symbol, candle.interval)

            if key in self._buffers:
                self._buffers[key].update(candle)

            # Publish to Redis for other agents
            if candle.is_closed:
                await self.bus.publish(
                    "chart/candle_closed",
                    orjson.dumps(candle.to_dict()),
                )

            # Notify callbacks
            for cb in self._callbacks:
                await cb(candle)

        except Exception as e:
            log.error("chart.parse_error", error=str(e))

    async def stop(self):
        self._running = False
        if self._ws and not self._ws.closed:
            await self._ws.close()
        if self._session and not self._session.closed:
            await self._session.close()
        log.info("chart.stopped")

    # ── Utility methods for agents ──────────────────────────

    def get_ohlcv_series(
        self, symbol: str, interval: str, count: int = 50
    ) -> list[dict]:
        """Get OHLCV data formatted for analysis / TA indicators."""
        buf = self.get_buffer(symbol, interval)
        if not buf:
            return []
        return buf.get_history(count)

    def get_price_change(self, symbol: str, interval: str, periods: int = 1) -> float | None:
        """Calculate price change over N periods."""
        history = self.get_ohlcv_series(symbol, interval, periods + 1)
        if len(history) < 2:
            return None
        return ((history[-1]["close"] - history[0]["close"]) / history[0]["close"]) * 100
