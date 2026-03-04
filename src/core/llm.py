"""
LLM Router — per-agent model assignments.

Each agent gets its own LLM based on task requirements:

    CEO  → gemini-3.1-pro-preview   (complex reasoning, decisions)
    CPO  → gemini-3.1-pro-preview   (portfolio analysis)
    CIO  → gemini-3-flash + Grok    (fast intel + X sentiment)
    CSO  → gemini-3.1-pro-preview   (market analysis)
    Assistant → gemini-3-flash       (lightweight housekeeping)
    CDO  → claude-opus-4-5          (code-level debugging)
    Telegram → gemini-3.1-pro-preview (main conversational agent)

Gemini: google-generativeai SDK
Grok:   OpenAI-compatible endpoint (api.x.ai)
Claude: anthropic SDK
"""
import aiohttp
import orjson
import structlog
from typing import Any
from dataclasses import dataclass

log = structlog.get_logger()

# ── Model Assignments ───────────────────────────────────────

AGENT_MODELS = {
    "ceo":       {"provider": "gemini", "model": "gemini-3.1-pro-preview"},
    "cpo":       {"provider": "gemini", "model": "gemini-3.1-pro-preview"},
    "cio":       {"provider": "gemini", "model": "gemini-3-flash"},
    "cso":       {"provider": "gemini", "model": "gemini-3.1-pro-preview"},
    "assistant": {"provider": "gemini", "model": "gemini-3-flash"},
    "cdo":       {"provider": "claude", "model": "claude-opus-4-5-20250514"},
    "codex":     {"provider": "claude", "model": "claude-opus-4-5-20250514"},
    "telegram":  {"provider": "gemini", "model": "gemini-3.1-pro-preview"},
}

# CIO also uses Grok for X/Twitter sentiment (in .py agent code only)
CIO_GROK_MODEL = "grok-3"

# ── Gemini Client ──────────────────────────────────────────

GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models"


class GeminiClient:
    """Async Gemini API client using REST (no SDK dependency)."""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self._session: aiohttp.ClientSession | None = None

    async def _ensure_session(self):
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    async def generate(
        self,
        model: str,
        prompt: str,
        system_instruction: str = "",
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> str | None:
        """Generate a completion from Gemini."""
        await self._ensure_session()

        url = f"{GEMINI_API_URL}/{model}:generateContent?key={self.api_key}"

        body: dict[str, Any] = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
            },
        }

        if system_instruction:
            body["systemInstruction"] = {
                "parts": [{"text": system_instruction}]
            }

        try:
            async with self._session.post(url, json=body) as resp:
                if resp.status != 200:
                    error = await resp.text()
                    log.error("gemini.error", model=model, status=resp.status, error=error[:200])
                    return None

                data = await resp.json()
                candidates = data.get("candidates", [])
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    if parts:
                        return parts[0].get("text", "")
                return None
        except Exception as e:
            log.error("gemini.request_failed", model=model, error=str(e))
            return None


# ── Grok Client (OpenAI-compatible) ────────────────────────


class GrokClient:
    """Async Grok/xAI client using OpenAI-compatible API."""

    def __init__(self, api_key: str, base_url: str = "https://api.x.ai/v1"):
        self.api_key = api_key
        self.base_url = base_url
        self._session: aiohttp.ClientSession | None = None

    async def _ensure_session(self):
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                headers={"Authorization": f"Bearer {self.api_key}"},
            )

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    async def generate(
        self,
        prompt: str,
        system_prompt: str = "",
        model: str = CIO_GROK_MODEL,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> str | None:
        """Generate a completion from Grok."""
        await self._ensure_session()

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        body = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        try:
            async with self._session.post(f"{self.base_url}/chat/completions", json=body) as resp:
                if resp.status != 200:
                    error = await resp.text()
                    log.error("grok.error", status=resp.status, error=error[:200])
                    return None

                data = await resp.json()
                choices = data.get("choices", [])
                if choices:
                    return choices[0].get("message", {}).get("content", "")
                return None
        except Exception as e:
            log.error("grok.request_failed", error=str(e))
            return None


# ── Claude Client ──────────────────────────────────────────


class ClaudeClient:
    """Async Claude API client for CDO agent."""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self._session: aiohttp.ClientSession | None = None

    async def _ensure_session(self):
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                headers={
                    "x-api-key": self.api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
            )

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    async def generate(
        self,
        prompt: str,
        system_prompt: str = "",
        model: str = "claude-opus-4-5-20250514",
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> str | None:
        """Generate a completion from Claude."""
        await self._ensure_session()

        body: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
        }
        if system_prompt:
            body["system"] = system_prompt

        try:
            async with self._session.post("https://api.anthropic.com/v1/messages", json=body) as resp:
                if resp.status != 200:
                    error = await resp.text()
                    log.error("claude.error", status=resp.status, error=error[:200])
                    return None

                data = await resp.json()
                content = data.get("content", [])
                if content:
                    return content[0].get("text", "")
                return None
        except Exception as e:
            log.error("claude.request_failed", error=str(e))
            return None


# ── LLM Router ─────────────────────────────────────────────


class LLMRouter:
    """
    Routes LLM calls to the correct provider/model per agent.

    Usage:
        router = LLMRouter(gemini_key, xai_key, anthropic_key)

        # Agent-specific call (auto-routes to correct model)
        response = await router.think("ceo", prompt, system_prompt)

        # CIO-specific: use Grok for X sentiment
        sentiment = await router.grok(prompt, system_prompt)

        # CDO-specific: use Claude for code analysis
        analysis = await router.claude(prompt, system_prompt)
    """

    def __init__(
        self,
        gemini_api_key: str,
        xai_api_key: str = "",
        anthropic_api_key: str = "",
        xai_base_url: str = "https://api.x.ai/v1",
    ):
        self.gemini = GeminiClient(gemini_api_key) if gemini_api_key else None
        self.grok_client = GrokClient(xai_api_key, xai_base_url) if xai_api_key else None
        self.claude_client = ClaudeClient(anthropic_api_key) if anthropic_api_key else None

    async def close(self):
        if self.gemini:
            await self.gemini.close()
        if self.grok_client:
            await self.grok_client.close()
        if self.claude_client:
            await self.claude_client.close()

    async def think(
        self,
        agent_name: str,
        prompt: str,
        system_prompt: str = "",
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> str | None:
        """
        Route an LLM call to the correct provider/model for this agent.

        agent_name: "ceo", "cpo", "cio", "cso", "assistant", "cdo", "telegram"
        """
        config = AGENT_MODELS.get(agent_name)
        if not config:
            log.error("llm.unknown_agent", agent=agent_name)
            return None

        provider = config["provider"]
        model = config["model"]

        log.debug("llm.routing", agent=agent_name, provider=provider, model=model)

        if provider == "gemini" and self.gemini:
            return await self.gemini.generate(
                model=model,
                prompt=prompt,
                system_instruction=system_prompt,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        elif provider == "claude" and self.claude_client:
            return await self.claude_client.generate(
                prompt=prompt,
                system_prompt=system_prompt,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        else:
            log.error("llm.provider_not_configured", provider=provider, agent=agent_name)
            return None

    async def grok(
        self,
        prompt: str,
        system_prompt: str = "",
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> str | None:
        """Direct Grok call — used by CIO for X/Twitter sentiment analysis."""
        if not self.grok_client:
            log.error("llm.grok_not_configured")
            return None
        return await self.grok_client.generate(
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    async def claude(
        self,
        prompt: str,
        system_prompt: str = "",
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> str | None:
        """Direct Claude call — used by CDO for code analysis."""
        if not self.claude_client:
            log.error("llm.claude_not_configured")
            return None
        return await self.claude_client.generate(
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
        )
