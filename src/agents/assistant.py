"""Assistant Agent — memory, timestamps, housekeeping. Handles non-critical tasks."""
from src.agents.base import BaseAgent


class AssistantAgent(BaseAgent):
    name = "assistant"
    subscribe_channels = ["ceo/decisions", "system/cycle"]

    async def on_start(self):
        self.log.info("ready")

    async def on_stop(self):
        pass

    async def on_message(self, channel: str, data: dict):
        self.log.info("message_received", channel=channel)
        # TODO: log decisions, save memories, timestamp events

    async def on_cycle(self):
        # TODO: housekeeping — prune old logs, summarize activity
        self.log.info("cycle_tick")
