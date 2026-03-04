# CLAUDE.md — Project Context for Claude Code

## What This Is
A multi-agent trading infrastructure for Polymarket. Six async agents run in a single
Python process, communicating via Redis pub/sub. The stack connects to an existing
n8n + Redis deployment via Docker networking.

## Tech Stack
- Python 3.12, asyncio, aiohttp
- Redis pub/sub (message bus) + key/value (shared state + caching)
- Polymarket py-clob-client for trade execution
- xAI/Grok API (OpenAI-compatible) for sentiment analysis
- Elfa AI API v2 for trending tokens, social mentions, narratives
- Binance WebSocket for real-time crypto charts (no API key needed)
- n8n for scheduling and workflow automation
- Docker Compose on Ubuntu 24 VPS (2-4 CPU, 4-8GB RAM)

## Project Structure
```
src/main.py          → Entry point, starts all agents + chart stream
src/core/bus.py      → Redis pub/sub wrapper
src/core/cache.py    → Redis-backed caching with TTL (cache-aside pattern)
src/core/config.py   → Pydantic settings from .env
src/core/scheduler.py → 30-min cycle trigger
src/core/webhook.py  → HTTP endpoint for n8n callbacks
src/integrations/
├── elfa.py          → Elfa AI REST API v2 client (cached)
├── charts.py        → Binance WebSocket real-time kline/candles
├── telegram.py      → Admin commands + notifications
├── proxy.py         → IPRoyal proxy rotation with country fallback
src/agents/base.py   → BaseAgent abstract class (has self.cache, self.elfa, self.charts)
src/agents/ceo.py    → Decision maker, executes trades
src/agents/cio.py    → Grok + Elfa + Charts intelligence gathering
src/agents/cso.py    → Market scouting
src/agents/cpo.py    → Portfolio monitoring with real-time charts
src/agents/cdo.py    → System health
src/agents/assistant.py → Memory & housekeeping
skills/*.md          → Agent behavior definitions
```

## Key Patterns
- All agents inherit from BaseAgent and implement on_start, on_stop, on_message, on_cycle
- Agents communicate via Redis channels (see README.md for channel map)
- Each agent has self.cache, self.elfa, self.charts injected via ctx dict
- Each agent loads its skills/*.md file at startup for behavior rules
- State persists to /app/data/state/ as JSON
- The orchestrator container joins n8n_default Docker network to reach Redis

## Caching Strategy
- Redis-backed cache with TTL per data source (see src/core/cache.py CACHE_TTL)
- Cache-aside pattern: cache.get_or_fetch(key, fetch_fn, ttl)
- Elfa API: 100 req/min limit → cache trending tokens 5 min, mentions 2-3 min
- Polymarket: positions cached 1 min, orderbook 30 sec
- Binance charts: real-time via WebSocket, REST fallback cached 1 min

## Real-Time Charts
- Binance WebSocket streams kline data (no API key)
- Default pairs: BTCUSDT, ETHUSDT, SOLUSDT, XRPUSDT at 15m + 1h intervals
- In-memory ChartBuffer (200 candles per pair/interval) + Redis pub/sub
- Closed candles published to chart/candle_closed channel
- CPO + CIO both consume chart signals

## Elfa AI Integration
- REST API v2: https://api.elfa.ai/v2/
- Auth: x-elfa-api-key header
- Endpoints: trending-tokens, trending-narratives, top-mentions, keyword-mentions, token-news
- All calls go through Cache layer automatically

## Telegram Bot
- Long-polling bot for admin commands + notifications
- Only responds to TG_ADMIN_CHAT_ID (single admin)
- Commands: /status, /prices, /trending, /cycle, /cache, /proxy, /help
- Auto-notifies on: CEO decisions, CPO alerts, CDO health issues, CIO chart signals
- Agents can send messages via self.telegram.notify()

## LLM Routing (per-agent models)
Each agent is assigned a specific LLM via `src/core/llm.py`:

| Agent     | Provider | Model                    | Purpose                    |
|-----------|----------|--------------------------|----------------------------|
| CEO       | Gemini   | gemini-3.1-pro-preview   | Complex decisions          |
| CPO       | Gemini   | gemini-3.1-pro-preview   | Portfolio analysis         |
| CIO       | Gemini   | gemini-3-flash           | Fast intel (+ Grok in .py) |
| CSO       | Gemini   | gemini-3.1-pro-preview   | Market analysis            |
| Assistant | Gemini   | gemini-3-flash           | Lightweight housekeeping   |
| CDO       | Claude   | claude-opus-4-5          | System health debugging    |
| Codex     | Claude   | claude-opus-4-5          | Autonomous coding agent    |
| Telegram  | Gemini   | gemini-3.1-pro-preview   | Main conversational agent  |

Agents call `await self.think(prompt, system_prompt)` — auto-routes to their assigned model.
CIO also calls `await self.llm.grok(prompt)` for X/Twitter sentiment (in .py code only, not skill files).
CDO/Codex call `await self.llm.claude(prompt)` for deep code analysis via Claude Opus.
Telegram: commands → hardcoded handlers; free text → Gemini 3.1 Pro with live context.

## Proxy Rotation (IPRoyal)
- Input format: HOST:PORT:USER:PASS (set as POLY_PROXY_URL)
- IPRoyal country targeting: appends _country-XX to username
- On Polymarket rejection → auto-rotates to next country
- Failed countries get 5-min cooldown before retrying
- If all 20 countries exhausted → cooldowns reset, cycle restarts
- Use `execute_with_proxy_rotation(self.proxy, fn)` for all trade execution
- `/proxy` Telegram command shows rotation stats
- Countries tried: random → US → CA → GB → DE → FR → NL → BR → AU → JP → etc.

## Development Workflow
Source code is baked into both container images (no bind mounts).
To edit and test changes:

1. Enter claude-dev: `docker exec -it claude-dev bash` → `claude`
2. Edit files at `/workspace/src/`
3. Test locally inside claude-dev: `PYTHONPATH=/workspace python3 -m src.main`
4. From the VPS host (not inside claude-dev), push + restart:
   ```
   docker cp claude-dev:/workspace/src/. /path/to/repo/src/
   docker restart agent-orchestrator
   ```

Or: push to GitHub and redeploy from hosting panel.

## Environment Variables
Passed via hosting panel Environment section, or `source .secrets` locally.
Naming convention: SERVICE_PURPOSE

| Variable                 | Service      | Required |
|--------------------------|-------------|----------|
| `ANTHROPIC_API_KEY`      | Claude Code | Yes      |
| `XAI_API_KEY`            | Grok        | Yes      |
| `ELFA_API_KEY`           | Elfa AI     | Yes      |
| `POLY_WALLET_PRIVATE_KEY`| Polymarket  | Yes      |
| `POLY_WALLET_ADDRESS`    | Polymarket  | Yes      |
| `POLY_PROXY_URL`         | IPRoyal     | Yes      |

Format: `HOST:PORT:USER:PASS` (e.g., `geo.iproyal.com:12321:user:pass`)
ProxyManager parses this and handles country rotation automatically.
| `POLY_RPC_URL`           | Chainstack  | Yes      |
| `TG_BOT_TOKEN`           | Telegram    | Yes      |
| `TG_ADMIN_CHAT_ID`       | Telegram    | Yes      |
| `OPENROUTER_API_KEY`     | OpenRouter  | No       |
| `CHART_PAIRS`            | Binance     | No       |
| `CHART_INTERVALS`        | Binance     | No       |

No POLY_API_KEY/SECRET/PASSPHRASE — execution goes through wallet + proxy only.
POLY_RPC_URL is your Chainstack Polygon node — use this instead of public RPCs for reliable tx execution.

## Commands
- `docker compose up -d` — start the stack
- `docker exec -it claude-dev bash` — enter dev container
- `python -m src.main` — run orchestrator locally
- `pytest tests/` — run tests

## Important Notes
- Redis is on the n8n_default network, hostname: `redis`, port: 6379
- n8n is at `n8n-n8n-1:5678` on the same network
- Wallet private key is in .env — NEVER log or expose it
- All trade decisions must be logged with reasoning before execution
