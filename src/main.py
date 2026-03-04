"""
Agent Orchestrator — Entry Point
Starts all agent coroutines in a single async event loop.
"""
import asyncio
import signal
import structlog

from src.core.config import Settings
from src.core.bus import MessageBus
from src.core.cache import Cache
from src.core.scheduler import Scheduler
from src.core.webhook import WebhookServer
from src.core.llm import LLMRouter

from src.integrations.elfa import ElfaClient
from src.integrations.charts import BinanceChartClient
from src.integrations.telegram import TelegramBot
from src.integrations.proxy import ProxyManager

from src.agents.ceo import CEOAgent
from src.agents.cio import CIOAgent
from src.agents.cso import CSOAgent
from src.agents.cpo import CPOAgent
from src.agents.cdo import CDOAgent
from src.agents.assistant import AssistantAgent
from src.agents.codex import CodexAgent

log = structlog.get_logger()

# Default crypto pairs to track for UP/DOWN positions
DEFAULT_CHART_PAIRS = [
    ("BTCUSDT", "1h"),
    ("BTCUSDT", "15m"),
    ("ETHUSDT", "1h"),
    ("ETHUSDT", "15m"),
    ("SOLUSDT", "1h"),
    ("XRPUSDT", "1h"),
]


async def main():
    settings = Settings()

    # ── Core services ───────────────────────────────────────
    bus = MessageBus(settings.redis_host, settings.redis_port)
    await bus.connect()

    cache = Cache(bus)

    # ── LLM Router (per-agent model assignments) ───────────
    llm = LLMRouter(
        gemini_api_key=settings.gemini_api_key,
        xai_api_key=settings.xai_api_key,
        anthropic_api_key=settings.anthropic_api_key,
        xai_base_url=settings.xai_base_url,
    )

    # ── Integration clients ─────────────────────────────────
    elfa = ElfaClient(api_key=settings.elfa_api_key, cache=cache)
    charts = BinanceChartClient(bus=bus)

    # Proxy manager for Polymarket execution
    proxy = None
    if settings.poly_proxy_url:
        proxy = ProxyManager.from_env(settings.poly_proxy_url)
        proxy.shuffle_countries()  # Randomize on startup
        log.info("proxy.enabled", host=proxy.host)
    else:
        log.warning("proxy.disabled", reason="POLY_PROXY_URL not set")

    # Subscribe to default crypto pairs
    for symbol, interval in DEFAULT_CHART_PAIRS:
        await charts.subscribe(symbol, interval)

    # ── Shared context for all agents ───────────────────────
    ctx = {
        "cache": cache,
        "elfa": elfa,
        "charts": charts,
        "proxy": proxy,
        "llm": llm,
    }

    # ── Telegram bot (admin interface + notifications) ──────
    tg = None
    if settings.tg_bot_token and settings.tg_admin_chat_id:
        tg = TelegramBot(
            token=settings.tg_bot_token,
            admin_chat_id=settings.tg_admin_chat_id,
            bus=bus,
            cache=cache,
            charts=charts,
            elfa=elfa,
            proxy=proxy,
            llm=llm,
        )
        ctx["telegram"] = tg
        log.info("telegram.enabled", admin_chat_id=settings.tg_admin_chat_id)
    else:
        log.warning("telegram.disabled", reason="TG_BOT_TOKEN or TG_ADMIN_CHAT_ID not set")

    # ── Initialize agents ───────────────────────────────────
    agents = [
        CEOAgent(bus, settings, ctx),
        CIOAgent(bus, settings, ctx),
        CSOAgent(bus, settings, ctx),
        CPOAgent(bus, settings, ctx),
        CDOAgent(bus, settings, ctx),
        CodexAgent(bus, settings, ctx),
        AssistantAgent(bus, settings, ctx),
    ]

    # ── Infrastructure ──────────────────────────────────────
    webhook = WebhookServer(bus, port=8080)
    scheduler = Scheduler(bus, interval_minutes=settings.analysis_interval)

    # ── Start everything ────────────────────────────────────
    tasks = [agent.run() for agent in agents]
    tasks.append(webhook.start())
    tasks.append(scheduler.start())
    tasks.append(charts.start())  # Binance WebSocket stream
    if tg:
        tasks.append(tg.start())  # Telegram long-polling

    log.info(
        "orchestrator.starting",
        agent_count=len(agents),
        chart_pairs=len(DEFAULT_CHART_PAIRS),
        cache="redis",
        elfa="enabled" if settings.elfa_api_key else "disabled",
        telegram="enabled" if tg else "disabled",
    )

    # Graceful shutdown
    loop = asyncio.get_event_loop()
    shutdown_resources = (agents, bus, elfa, charts, tg, llm)
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(
            sig, lambda: asyncio.create_task(shutdown(*shutdown_resources))
        )

    await asyncio.gather(*tasks)


async def shutdown(agents, bus, elfa, charts, tg, llm):
    log.info("orchestrator.shutting_down")
    if tg:
        await tg.stop()
    await charts.stop()
    await elfa.close()
    await llm.close()
    for agent in agents:
        await agent.stop()
    await bus.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
