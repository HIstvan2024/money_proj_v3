"""
Telegram Bot — admin command interface + notification system.

Runs as a long-polling loop inside the orchestrator.
Only responds to TG_ADMIN_CHAT_ID — all other messages are ignored.

Commands:
  /status        — agent health + cache stats
  /portfolio     — current positions + P&L
  /prices        — live prices for tracked pairs
  /trending      — Elfa trending tokens
  /cycle         — force a 30-min analysis cycle
  /buy <market>  — manual buy (requires confirmation)
  /sell <market> — manual sell (requires confirmation)
  /help          — list commands

Notifications (outbound):
  - CEO decisions (buy/sell/hold)
  - CPO alerts (position threshold breaches)
  - CDO alerts (system health issues)
  - CIO signals (significant chart moves)
"""
import asyncio
import aiohttp
import orjson
import structlog
from datetime import datetime, timezone
from typing import Callable, Awaitable

log = structlog.get_logger()

TG_API = "https://api.telegram.org/bot{token}"


class TelegramBot:
    """Async Telegram bot for admin control + notifications."""

    def __init__(self, token: str, admin_chat_id: str, bus=None, cache=None, charts=None, elfa=None, proxy=None, llm=None):
        self.token = token
        self.admin_chat_id = str(admin_chat_id)
        self.bus = bus
        self.cache = cache
        self.charts = charts
        self.elfa = elfa
        self.proxy = proxy
        self.llm = llm
        self._base_url = TG_API.format(token=token)
        self._session: aiohttp.ClientSession | None = None
        self._running = False
        self._offset = 0
        self._commands: dict[str, Callable] = {}
        self._pending_confirm: dict[str, dict] = {}

        # Register built-in commands
        self._register_commands()

    def _register_commands(self):
        self._commands = {
            "/start": self._cmd_help,
            "/help": self._cmd_help,
            "/status": self._cmd_status,
            "/prices": self._cmd_prices,
            "/trending": self._cmd_trending,
            "/cycle": self._cmd_force_cycle,
            "/cache": self._cmd_cache_stats,
            "/proxy": self._cmd_proxy_stats,
            "/codex": self._cmd_codex,
            "/yes": self._cmd_confirm,
            "/no": self._cmd_cancel,
        }

    async def _ensure_session(self):
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()

    async def _api(self, method: str, data: dict | None = None) -> dict | None:
        """Call Telegram Bot API."""
        await self._ensure_session()
        url = f"{self._base_url}/{method}"
        try:
            async with self._session.post(url, json=data or {}) as resp:
                if resp.status == 200:
                    result = await resp.json()
                    return result.get("result")
                else:
                    text = await resp.text()
                    log.error("tg.api_error", method=method, status=resp.status, body=text)
                    return None
        except Exception as e:
            log.error("tg.request_failed", method=method, error=str(e))
            return None

    # ── Outbound: Notifications ─────────────────────────────

    async def notify(self, text: str, parse_mode: str = "HTML"):
        """Send a notification to the admin."""
        await self._api("sendMessage", {
            "chat_id": self.admin_chat_id,
            "text": text,
            "parse_mode": parse_mode,
        })

    async def notify_decision(self, decision: dict):
        """Format and send a CEO decision notification."""
        action = decision.get("action", "unknown").upper()
        emoji = {"BUY": "🟢", "SELL": "🔴", "HOLD": "🟡"}.get(action, "⚪")
        msg = (
            f"{emoji} <b>CEO Decision: {action}</b>\n\n"
            f"Market: <code>{decision.get('market_id', 'N/A')}</code>\n"
            f"Amount: {decision.get('amount', 'N/A')}\n"
            f"Confidence: {decision.get('confidence', 'N/A')}\n\n"
            f"<i>{decision.get('reasoning', '')}</i>"
        )
        await self.notify(msg)

    async def notify_alert(self, alert: dict):
        """Format and send a CPO/CDO alert."""
        alert_type = alert.get("alert_type", "unknown")
        symbol = alert.get("symbol", "N/A")
        msg = (
            f"⚠️ <b>Alert: {alert_type}</b>\n\n"
            f"Symbol: <code>{symbol}</code>\n"
            f"Change 1h: {alert.get('change_1h', 'N/A')}%\n"
            f"Change 4h: {alert.get('change_4h', 'N/A')}%\n"
            f"Price: {alert.get('current_price', 'N/A')}\n"
            f"Recommendation: {alert.get('recommendation', 'N/A')}"
        )
        await self.notify(msg)

    async def notify_chart_signal(self, signal: dict):
        """Format and send a CIO chart signal."""
        direction = signal.get("direction", "")
        emoji = "📈" if direction == "up" else "📉"
        msg = (
            f"{emoji} <b>Chart Signal</b>\n\n"
            f"Symbol: <code>{signal.get('symbol', 'N/A')}</code>\n"
            f"Interval: {signal.get('interval', 'N/A')}\n"
            f"Change: {signal.get('change_pct', 'N/A')}%"
        )
        await self.notify(msg)

    # ── Inbound: Command Handling ───────────────────────────

    async def start(self):
        """Start long-polling for Telegram updates."""
        self._running = True
        log.info("tg.started", admin=self.admin_chat_id)

        # Subscribe to bus channels for auto-notifications
        if self.bus:
            await self.bus.subscribe("ceo/decisions", self._on_ceo_decision)
            await self.bus.subscribe("cpo/alerts", self._on_cpo_alert)
            await self.bus.subscribe("cdo/health", self._on_cdo_health)
            await self.bus.subscribe("cio/intel", self._on_cio_intel)

        while self._running:
            try:
                updates = await self._api("getUpdates", {
                    "offset": self._offset,
                    "timeout": 30,
                    "allowed_updates": ["message"],
                })
                if updates:
                    for update in updates:
                        await self._process_update(update)
                        self._offset = update["update_id"] + 1
            except Exception as e:
                log.error("tg.poll_error", error=str(e))
                await asyncio.sleep(5)

    async def stop(self):
        self._running = False
        if self._session and not self._session.closed:
            await self._session.close()
        log.info("tg.stopped")

    async def _process_update(self, update: dict):
        """Process a single Telegram update."""
        message = update.get("message", {})
        chat_id = str(message.get("chat", {}).get("id", ""))
        text = message.get("text", "").strip()

        # Only respond to admin
        if chat_id != self.admin_chat_id:
            log.warning("tg.unauthorized", chat_id=chat_id)
            return

        if not text:
            return

        # Route to command handler
        cmd = text.split()[0].lower()
        handler = self._commands.get(cmd)
        if handler:
            await handler(text)
        elif text.startswith("/"):
            await self.notify(f"Unknown command: <code>{cmd}</code>\nType /help for available commands.")
        else:
            # Non-command message → route to Gemini 3.1 Pro conversational agent
            await self._handle_chat(text)

    # ── Bus event handlers (auto-notify) ────────────────────

    async def _on_ceo_decision(self, channel: str, data: bytes):
        parsed = orjson.loads(data)
        await self.notify_decision(parsed)

    async def _on_cpo_alert(self, channel: str, data: bytes):
        parsed = orjson.loads(data)
        await self.notify_alert(parsed)

    async def _on_cdo_health(self, channel: str, data: bytes):
        parsed = orjson.loads(data)
        if parsed.get("status") == "error":
            await self.notify(f"🚨 <b>System Health Issue</b>\n\n{parsed.get('message', 'Unknown error')}")

    async def _on_cio_intel(self, channel: str, data: bytes):
        parsed = orjson.loads(data)
        if parsed.get("type") == "chart_signal":
            await self.notify_chart_signal(parsed.get("data", {}))

    # ── Command implementations ─────────────────────────────

    async def _cmd_help(self, text: str):
        msg = (
            "🤖 <b>Agent Stack Commands</b>\n\n"
            "/status — Agent health overview\n"
            "/prices — Live crypto prices\n"
            "/trending — Elfa trending tokens\n"
            "/cycle — Force analysis cycle\n"
            "/cache — Cache hit/miss stats\n"
            "/proxy — Proxy rotation stats\n"
            "/codex &lt;task&gt; — Coding task (Opus)\n"
            "/help — This message\n\n"
            "<i>Or just type a message to chat with the main agent.</i>"
        )
        await self.notify(msg)

    async def _cmd_status(self, text: str):
        now = datetime.now(timezone.utc).strftime("%H:%M:%S UTC")
        lines = [f"📊 <b>Status</b> ({now})\n"]

        # Chart prices
        if self.charts:
            for symbol in ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]:
                price = self.charts.get_price(symbol, "1h")
                if price:
                    lines.append(f"  {symbol}: ${price:,.2f}")

        # Cache stats
        if self.cache:
            stats = self.cache.stats()
            lines.append(f"\nCache: {stats['hit_rate']} hit rate ({stats['hits']}h/{stats['misses']}m)")

        # Proxy stats
        if self.proxy:
            ps = self.proxy.stats()
            lines.append(f"\nProxy: {ps['current_country']} (last ok: {ps['last_success']})")
            lines.append(f"  Available: {ps['available_countries']} countries, {ps['cooled_down_countries']} cooling")

        await self.notify("\n".join(lines))

    async def _cmd_prices(self, text: str):
        if not self.charts:
            await self.notify("Charts not available.")
            return

        lines = ["💰 <b>Live Prices</b>\n"]
        for symbol in ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]:
            price = self.charts.get_price(symbol, "1h")
            change = self.charts.get_price_change(symbol, "1h", periods=1)
            if price:
                emoji = "🟢" if (change and change > 0) else "🔴" if (change and change < 0) else "⚪"
                change_str = f"{change:+.2f}%" if change else "N/A"
                lines.append(f"{emoji} {symbol}: <b>${price:,.2f}</b> ({change_str})")
        await self.notify("\n".join(lines))

    async def _cmd_trending(self, text: str):
        if not self.elfa:
            await self.notify("Elfa AI not configured.")
            return

        trending = await self.elfa.get_trending_tokens(time_window="1h", page_size=10)
        if not trending or not trending.get("data"):
            await self.notify("No trending data available.")
            return

        lines = ["🔥 <b>Trending Tokens (1h)</b>\n"]
        for i, token in enumerate(trending.get("data", [])[:10], 1):
            name = token.get("token", {}).get("name", "Unknown")
            mentions = token.get("mention_count", 0)
            lines.append(f"{i}. {name} — {mentions} mentions")
        await self.notify("\n".join(lines))

    async def _cmd_force_cycle(self, text: str):
        if self.bus:
            await self.bus.publish("system/cycle", orjson.dumps({
                "event": "analysis_cycle",
                "source": "telegram_admin",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }))
            await self.notify("⚡ Analysis cycle triggered.")
        else:
            await self.notify("Bus not available.")

    async def _cmd_cache_stats(self, text: str):
        if not self.cache:
            await self.notify("Cache not available.")
            return
        stats = self.cache.stats()
        msg = (
            f"📦 <b>Cache Stats</b>\n\n"
            f"Hits: {stats['hits']}\n"
            f"Misses: {stats['misses']}\n"
            f"Sets: {stats['sets']}\n"
            f"Hit rate: <b>{stats['hit_rate']}</b>"
        )
        await self.notify(msg)

    async def _cmd_proxy_stats(self, text: str):
        if not self.proxy:
            await self.notify("Proxy not configured.")
            return
        ps = self.proxy.stats()
        msg = (
            f"🌐 <b>Proxy Stats</b>\n\n"
            f"Current: <code>{ps['current_country']}</code>\n"
            f"Last success: <code>{ps['last_success']}</code>\n"
            f"Available countries: {ps['available_countries']}\n"
            f"In cooldown: {ps['cooled_down_countries']}\n"
            f"Recent: ✅ {ps['recent_successes']} / ❌ {ps['recent_failures']}"
        )
        await self.notify(msg)

    async def _cmd_codex(self, text: str):
        """Submit a coding task to the Codex agent (Opus-powered)."""
        task = text.replace("/codex", "", 1).strip()
        if not task:
            await self.notify("Usage: <code>/codex &lt;describe your coding task&gt;</code>")
            return

        if self.bus:
            await self.bus.publish("codex/tasks", orjson.dumps({
                "task": task,
                "source": "telegram",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }))
            await self.notify(f"🧬 Codex task submitted:\n<i>{task[:500]}</i>\n\nProcessing with Claude Opus...")
        else:
            await self.notify("Bus not available.")

    async def _cmd_confirm(self, text: str):
        if not self._pending_confirm:
            await self.notify("Nothing pending confirmation.")
            return
        # Execute the most recent pending action
        key = list(self._pending_confirm.keys())[-1]
        action = self._pending_confirm.pop(key)
        await self.notify(f"✅ Confirmed: {action.get('description', 'action')}")
        # TODO: route to CEO for execution

    async def _cmd_cancel(self, text: str):
        if self._pending_confirm:
            self._pending_confirm.clear()
            await self.notify("❌ All pending actions cancelled.")
        else:
            await self.notify("Nothing to cancel.")

    async def _handle_chat(self, text: str):
        """Handle non-command messages via Gemini 3.1 Pro (main conversational agent)."""
        if not self.llm:
            await self.notify("LLM not configured.")
            return

        # Build context with current system state
        context_parts = ["You are the main trading agent interface. Respond concisely."]

        # Inject live prices if available
        if self.charts:
            prices = []
            for symbol in ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]:
                price = self.charts.get_price(symbol, "1h")
                change = self.charts.get_price_change(symbol, "1h", periods=1)
                if price:
                    prices.append(f"{symbol}: ${price:,.2f} ({change:+.2f}%)" if change else f"{symbol}: ${price:,.2f}")
            if prices:
                context_parts.append(f"Current prices: {', '.join(prices)}")

        # Inject proxy status
        if self.proxy:
            ps = self.proxy.stats()
            context_parts.append(f"Proxy: {ps['current_country']} (last ok: {ps['last_success']})")

        system_prompt = "\n".join(context_parts)

        response = await self.llm.think(
            agent_name="telegram",
            prompt=text,
            system_prompt=system_prompt,
        )

        if response:
            # Telegram has a 4096 char limit per message
            if len(response) > 4000:
                for i in range(0, len(response), 4000):
                    await self.notify(response[i:i+4000], parse_mode="")
            else:
                await self.notify(response, parse_mode="")
        else:
            await self.notify("Couldn't generate a response. Check LLM configuration.")
