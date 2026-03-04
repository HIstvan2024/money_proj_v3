"""CSO Agent — market scout. Discovers new positions on Polymarket every hour."""
from src.agents.base import BaseAgent


class CSOAgent(BaseAgent):
    name = "cso"
    subscribe_channels = ["cio/intel", "system/cycle"]

    async def on_start(self):
        self.log.info("ready")

    async def on_stop(self):
        pass

    async def on_message(self, channel: str, data: dict):
        self.log.info("message_received", channel=channel)
        # TODO: scout markets, publish to cso/opportunities

    async def on_cycle(self):
        # TODO: scan for new positions
        self.log.info("cycle_tick")
