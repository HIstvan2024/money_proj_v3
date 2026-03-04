"""Webhook server — receives callbacks from n8n and external triggers."""
import orjson
from aiohttp import web
import structlog

from src.core.bus import MessageBus

log = structlog.get_logger()


class WebhookServer:
    def __init__(self, bus: MessageBus, port: int = 8080):
        self.bus = bus
        self.port = port

    async def start(self):
        app = web.Application()
        app.router.add_get("/health", self._health)
        app.router.add_post("/trigger/cycle", self._trigger_cycle)
        app.router.add_post("/trigger/{agent}", self._trigger_agent)

        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", self.port)
        await site.start()
        log.info("webhook.started", port=self.port)

        # Keep running
        while True:
            await __import__("asyncio").sleep(3600)

    async def _health(self, request: web.Request) -> web.Response:
        return web.json_response({"status": "ok"})

    async def _trigger_cycle(self, request: web.Request) -> web.Response:
        """n8n can POST here to trigger an analysis cycle."""
        data = await request.json() if request.can_read_body else {}
        await self.bus.publish("system/cycle", orjson.dumps({
            "event": "analysis_cycle",
            "source": "n8n",
            **data,
        }))
        log.info("webhook.cycle_triggered", source="n8n")
        return web.json_response({"triggered": True})

    async def _trigger_agent(self, request: web.Request) -> web.Response:
        """POST /trigger/{agent} — send a direct message to a specific agent."""
        agent = request.match_info["agent"]
        data = await request.json() if request.can_read_body else {}
        channel = f"{agent}/trigger"
        await self.bus.publish(channel, orjson.dumps(data))
        log.info("webhook.agent_triggered", agent=agent)
        return web.json_response({"triggered": True, "agent": agent})
