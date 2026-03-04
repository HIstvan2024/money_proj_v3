"""CDO Agent — system health monitor. Alerts on failures, has sudo access."""
from src.agents.base import BaseAgent


class CDOAgent(BaseAgent):
    name = "cdo"
    subscribe_channels = ["system/cycle"]

    async def on_start(self):
        self.log.info("ready")

    async def on_stop(self):
        pass

    async def on_message(self, channel: str, data: dict):
        self.log.info("message_received", channel=channel)
        # TODO: health checks, publish to cdo/health

    async def on_cycle(self):
        # TODO: run diagnostics
        self.log.info("cycle_tick")
