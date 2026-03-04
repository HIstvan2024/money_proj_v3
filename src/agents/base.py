"""
BaseAgent — Abstract async agent with lifecycle management.
All agents inherit from this and implement their specific logic.
"""
import asyncio
from pathlib import Path
from abc import ABC, abstractmethod
import structlog
import orjson

from src.core.bus import MessageBus
from src.core.config import Settings


class BaseAgent(ABC):
    """Base class for all agents in the orchestrator."""

    name: str = "base"
    subscribe_channels: list[str] = []

    def __init__(self, bus: MessageBus, settings: Settings, ctx: dict | None = None):
        self.bus = bus
        self.settings = settings
        self.ctx = ctx or {}
        self.cache = ctx.get("cache") if ctx else None
        self.elfa = ctx.get("elfa") if ctx else None
        self.charts = ctx.get("charts") if ctx else None
        self.telegram = ctx.get("telegram") if ctx else None
        self.proxy = ctx.get("proxy") if ctx else None
        self.llm = ctx.get("llm") if ctx else None
        self.log = structlog.get_logger().bind(agent=self.name)
        self._running = False
        self._skill: str | None = None

    async def run(self):
        """Main agent lifecycle."""
        self._running = True
        self._load_skill()

        # Subscribe to channels
        for channel in self.subscribe_channels:
            await self.bus.subscribe(channel, self._handle_message)

        self.log.info("agent.started", channels=self.subscribe_channels)
        await self.on_start()

        while self._running:
            await asyncio.sleep(1)

    async def stop(self):
        """Graceful shutdown."""
        self._running = False
        await self.on_stop()
        self.log.info("agent.stopped")

    def _load_skill(self):
        """Load the agent's skill.md file."""
        skill_path = Path(f"/app/skills/{self.name}.md")
        if skill_path.exists():
            self._skill = skill_path.read_text()
            self.log.info("agent.skill_loaded", path=str(skill_path))
        else:
            self.log.warning("agent.no_skill_file", path=str(skill_path))

    async def publish(self, channel: str, data: dict):
        """Publish a message to a Redis channel."""
        await self.bus.publish(channel, orjson.dumps(data))

    async def think(self, prompt: str, system_prompt: str = "", **kwargs) -> str | None:
        """
        Call the agent's assigned LLM model.
        Auto-routes to the correct provider/model based on self.name.

        CEO/CPO/CSO → Gemini 3.1 Pro Preview
        CIO/Assistant → Gemini 3 Flash
        CDO → Claude Opus
        """
        if not self.llm:
            self.log.error("llm_not_available")
            return None

        # Use skill file as system prompt if none provided
        if not system_prompt and self._skill:
            system_prompt = self._skill

        return await self.llm.think(
            agent_name=self.name,
            prompt=prompt,
            system_prompt=system_prompt,
            **kwargs,
        )

    async def save_state(self, state: dict):
        """Persist agent state to disk."""
        state_path = Path(f"/app/data/state/{self.name}.json")
        state_path.write_bytes(orjson.dumps(state))

    async def load_state(self) -> dict | None:
        """Load persisted agent state."""
        state_path = Path(f"/app/data/state/{self.name}.json")
        if state_path.exists():
            return orjson.loads(state_path.read_bytes())
        return None

    async def _handle_message(self, channel: str, data: bytes):
        """Route incoming messages to the agent's handler."""
        try:
            parsed = orjson.loads(data)
            await self.on_message(channel, parsed)
        except Exception as e:
            self.log.error("agent.message_error", error=str(e), channel=channel)

    # ── Abstract methods (implement in each agent) ──────────

    @abstractmethod
    async def on_start(self):
        """Called once when the agent starts."""
        ...

    @abstractmethod
    async def on_stop(self):
        """Called once during graceful shutdown."""
        ...

    @abstractmethod
    async def on_message(self, channel: str, data: dict):
        """Handle an incoming message from the bus."""
        ...

    @abstractmethod
    async def on_cycle(self):
        """Called every 30-min analysis cycle."""
        ...
