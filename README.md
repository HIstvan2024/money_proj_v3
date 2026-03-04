# Agent Stack — Polymarket Trading Infrastructure

## Architecture

```
src/
├── main.py                 # Entry point — starts event loop + all agents
├── core/
│   ├── __init__.py
│   ├── bus.py              # Redis pub/sub message bus
│   ├── scheduler.py        # 30-min analysis cycle + event triggers
│   ├── webhook.py          # aiohttp server for n8n callbacks
│   └── config.py           # Pydantic settings from .env
├── agents/
│   ├── __init__.py
│   ├── base.py             # BaseAgent class (async lifecycle)
│   ├── ceo.py              # Chief Executive Officer — decision maker
│   ├── cio.py              # Chief Intelligence Officer — Grok + X scraping
│   ├── cso.py              # Chief Sales Officer — market scouting
│   ├── cpo.py              # Chief Portfolio Officer — position monitoring
│   ├── cdo.py              # Chief Developer Officer — system health
│   └── assistant.py        # Assistant — memory, timestamps, housekeeping

skills/                     # Agent skill definitions (loaded at init)
├── ceo.md
├── cio.md
├── cso.md
├── cpo.md
├── cdo.md
└── assistant.md

data/                       # Persistent volume (mounted at runtime)
├── state/                  # Agent state files (JSON)
├── logs/                   # Structured logs
└── memories/               # Conversation / decision history
```

## Message Bus Channels (Redis pub/sub)

| Channel             | Publisher | Subscribers     | Payload                     |
|---------------------|-----------|------------------|-----------------------------|
| `cio/intel`         | CIO       | CEO, CPO, CSO    | Sentiment data, X findings  |
| `cso/opportunities` | CSO       | CEO, CIO         | New market positions found  |
| `cpo/alerts`        | CPO       | CEO, CIO         | Position movement alerts    |
| `ceo/decisions`     | CEO       | All agents       | Buy/sell/hold directives    |
| `cdo/health`        | CDO       | CEO              | System health reports       |
| `chart/candle_closed`| Charts   | CIO, CPO         | Closed kline candle data    |
| `system/cycle`      | Scheduler | All agents       | 30-min analysis trigger     |

## Integrations

| Service       | Purpose                        | Auth            | Rate Limit     |
|---------------|--------------------------------|-----------------|----------------|
| Binance WS    | Real-time crypto charts        | None (public)   | Unlimited      |
| Elfa AI v2    | Trending tokens, social intel  | API key header  | 100 req/min    |
| Grok / xAI    | X sentiment, deep analysis     | API key         | Per plan       |
| Polymarket    | Trade execution, positions     | API key + wallet| Per plan       |

## Caching (Redis-backed)

All external API calls go through the cache-aside pattern. TTLs are tuned
per data source to balance freshness vs. rate limits. See `src/core/cache.py`.

## Quick Start

```bash
# 1. Copy secrets template
cp .secrets.example .secrets
# 2. Fill in your keys
nano .secrets
# 3. Source secrets and start
source .secrets && docker compose up -d
# 4. Enter Claude Code dev container
docker exec -it claude-dev bash
# 5. Start building
claude
```

## Telegram Commands

| Command             | Description                    |
|---------------------|--------------------------------|
| `/status`           | Agent health + cache + proxy   |
| `/prices`           | Live crypto prices             |
| `/trending`         | Elfa trending tokens           |
| `/cycle`            | Force 30-min analysis cycle    |
| `/cache`            | Cache hit/miss stats           |
| `/proxy`            | Proxy rotation stats           |
| `/codex <task>`     | Submit coding task (Opus)      |
| `/help`             | List commands                  |
| *free text*         | Chat with main agent (3.1 Pro) |

The bot also auto-sends notifications for CEO decisions, portfolio alerts,
system health issues, and significant chart moves.
