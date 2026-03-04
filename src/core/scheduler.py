"""Scheduler — triggers the 30-min analysis cycle via Redis pub/sub."""
import asyncio
import orjson
from datetime import datetime, timezone
import structlog

from src.core.bus import MessageBus

log = structlog.get_logger()


class Scheduler:
    def __init__(self, bus: MessageBus, interval_minutes: int = 30):
        self.bus = bus
        self.interval = interval_minutes * 60  # seconds

    async def start(self):
        log.info("scheduler.started", interval_minutes=self.interval // 60)
        while True:
            await asyncio.sleep(self.interval)
            cycle_data = {
                "event": "analysis_cycle",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "actions": ["analyze", "decide", "report"],
            }
            await self.bus.publish("system/cycle", orjson.dumps(cycle_data))
            log.info("scheduler.cycle_triggered")
