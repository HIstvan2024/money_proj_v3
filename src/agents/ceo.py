"""CEO Agent — autonomous decision maker. Gathers intel from CIO, CSO, CPO and executes trades."""
from src.agents.base import BaseAgent


class CEOAgent(BaseAgent):
    name = "ceo"
    subscribe_channels = ["cio/intel", "cso/opportunities", "cpo/alerts", "cdo/health", "system/cycle"]

    async def on_start(self):
        self.log.info("ready")

    async def on_stop(self):
        await self.save_state({"status": "shutdown"})

    async def on_message(self, channel: str, data: dict):
        self.log.info("message_received", channel=channel)
        # TODO: aggregate intel, reason, publish decisions to ceo/decisions

    async def on_cycle(self):
        # TODO: 30-min hold / buy / sell analysis
        self.log.info("cycle_tick")
