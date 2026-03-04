"""
Codex — Opus-Powered Coding Agent.

Autonomous code generation, review, debugging, and refactoring.
Powered by Claude Opus for deep code understanding.

Capabilities:
- Write new integrations, agents, and modules on request
- Debug runtime errors from CDO health reports
- Review and refactor existing codebase
- Generate tests for agent logic
- Hot-patch agent code during runtime

Trigger sources:
- CDO escalates code-level issues
- CEO requests new feature implementation
- Telegram /codex command for ad-hoc coding tasks
- system/cycle for periodic code health scans
"""
import asyncio
import orjson
import structlog
from datetime import datetime, timezone

from src.agents.base import BaseAgent

log = structlog.get_logger()


class CodexAgent(BaseAgent):
    """Opus-powered autonomous coding agent."""

    name = "codex"
    skill_file = "skills/codex.md"

    async def setup(self):
        """Subscribe to relevant channels."""
        await self.bus.subscribe("cdo/health", self._on_cdo_health)
        await self.bus.subscribe("ceo/decisions", self._on_ceo_request)
        await self.bus.subscribe("codex/tasks", self._on_task)
        self.log.info("codex.ready")

    async def cycle(self):
        """Periodic code health scan (every 30 min)."""
        # Codex doesn't run every cycle — only on demand
        pass

    async def _on_cdo_health(self, channel: str, data: bytes):
        """CDO escalated a code-level issue."""
        parsed = orjson.loads(data)
        if parsed.get("escalate_to") == "codex":
            error_info = parsed.get("error", "Unknown error")
            module = parsed.get("module", "unknown")

            self.log.info("codex.investigating", module=module)

            prompt = (
                f"A runtime error occurred in module `{module}`:\n\n"
                f"```\n{error_info}\n```\n\n"
                f"Analyze the error, identify the root cause, and provide a fix. "
                f"Include the corrected code."
            )

            response = await self.think(prompt)

            if response:
                await self.publish("codex/results", {
                    "type": "bug_fix",
                    "module": module,
                    "analysis": response,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })

                if self.telegram:
                    await self.telegram.notify(
                        f"🔧 <b>Codex: Bug Fix</b>\n\n"
                        f"Module: <code>{module}</code>\n\n"
                        f"{response[:3000]}"
                    )

    async def _on_ceo_request(self, channel: str, data: bytes):
        """CEO requested a new feature or code change."""
        parsed = orjson.loads(data)
        if parsed.get("action") == "codex_task":
            task = parsed.get("task", "")
            self.log.info("codex.ceo_task", task=task[:100])
            await self._execute_task(task)

    async def _on_task(self, channel: str, data: bytes):
        """Direct task submission (from Telegram /codex command)."""
        parsed = orjson.loads(data)
        task = parsed.get("task", "")
        if task:
            await self._execute_task(task)

    async def _execute_task(self, task: str):
        """Execute a coding task using Claude Opus."""
        self.log.info("codex.executing", task=task[:100])

        prompt = (
            f"You are a senior Python developer working on an async trading agent system. "
            f"The stack uses: Python 3.12, asyncio, aiohttp, Redis pub/sub, structlog, orjson.\n\n"
            f"Task: {task}\n\n"
            f"Provide complete, production-ready code. Include error handling, logging, "
            f"and type hints. Follow the existing codebase patterns."
        )

        response = await self.think(prompt, temperature=0.3, max_tokens=8192)

        if response:
            await self.publish("codex/results", {
                "type": "task_complete",
                "task": task[:200],
                "result": response,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })

            if self.telegram:
                # Truncate for Telegram
                preview = response[:2000]
                if len(response) > 2000:
                    preview += "\n\n... (truncated, full output in logs)"
                await self.telegram.notify(
                    f"🧬 <b>Codex: Task Complete</b>\n\n"
                    f"<i>{task[:200]}</i>\n\n"
                    f"<pre>{preview}</pre>",
                )
