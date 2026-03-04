"""Redis pub/sub message bus for inter-agent communication."""
import asyncio
from typing import Callable
import redis.asyncio as aioredis
import structlog

log = structlog.get_logger()


class MessageBus:
    def __init__(self, host: str, port: int, password: str = ""):
        self.host = host
        self.port = port
        self.password = password
        self._redis: aioredis.Redis | None = None
        self._pubsub: aioredis.client.PubSub | None = None
        self._handlers: dict[str, list[Callable]] = {}

    async def connect(self):
        self._redis = aioredis.Redis(
            host=self.host, port=self.port, password=self.password or None,
            decode_responses=False,
        )
        self._pubsub = self._redis.pubsub()
        await self._redis.ping()
        log.info("bus.connected", host=self.host, port=self.port)

    async def disconnect(self):
        if self._pubsub:
            await self._pubsub.close()
        if self._redis:
            await self._redis.close()
        log.info("bus.disconnected")

    async def subscribe(self, channel: str, handler: Callable):
        if channel not in self._handlers:
            self._handlers[channel] = []
            await self._pubsub.subscribe(channel)
        self._handlers[channel].append(handler)
        asyncio.create_task(self._listen())

    async def publish(self, channel: str, data: bytes):
        await self._redis.publish(channel, data)

    async def _listen(self):
        async for message in self._pubsub.listen():
            if message["type"] == "message":
                channel = message["channel"]
                if isinstance(channel, bytes):
                    channel = channel.decode()
                for handler in self._handlers.get(channel, []):
                    await handler(channel, message["data"])

    # ── Key/value state (for shared state, not just pub/sub) ──
    async def set(self, key: str, value: bytes, ttl: int | None = None):
        if ttl:
            await self._redis.setex(key, ttl, value)
        else:
            await self._redis.set(key, value)

    async def get(self, key: str) -> bytes | None:
        return await self._redis.get(key)
