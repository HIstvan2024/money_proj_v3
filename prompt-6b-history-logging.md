Read /docker/money_proj_v3/CLAUDE.md for project context.
Read /docker/money_proj_v3/src/agents/base.py for BaseAgent interface.
Read /docker/money_proj_v3/src/core/bus.py for Redis pub/sub.
Read /docker/money_proj_v3/src/core/cache.py for Redis cache.

TASK: Add agent activity history logging so the CGO can review all agent activity daily.

Every agent action — cycles, decisions, alerts, intel, errors — must be recorded
in Redis for the CGO to analyze later.

STEP 1 — Create src/core/history.py:

class AgentHistory:
    """
    Stores all agent activity in Redis lists for CGO daily review.
    
    Key pattern: history:{agent}:{date}
    Example: history:ceo:2026-03-05
    
    Each entry is a JSON object with timestamp, type, and data.
    Capped at 1000 entries per agent per day.
    Retained for 7 days, then auto-expired.
    """
    
    def __init__(self, redis_client):
        self.redis = redis_client
    
    async def log(self, agent: str, event_type: str, data: dict):
        """
        Log an agent event.
        
        agent: "ceo", "cio", "cso", "cpo", "cdo", "codex", "assistant"
        event_type: "cycle_start", "cycle_end", "decision", "alert", "intel",
                    "trade_executed", "trade_failed", "error", "opportunity",
                    "redeem", "health_check", "message_received", "message_sent"
        data: any dict with event details
        """
        # Key: history:{agent}:{YYYY-MM-DD}
        # Value: JSON with {timestamp, agent, event_type, data}
        # LPUSH + LTRIM to cap at 1000
        # EXPIRE key after 7 days (604800 seconds)
    
    async def get_agent_history(self, agent: str, date: str = None) -> list[dict]:
        """Get all events for an agent on a given date (default: today)."""
    
    async def get_all_history(self, date: str = None) -> dict[str, list]:
        """Get all agent events for a given date. Returns {agent: [events]}."""
    
    async def get_trades(self, date: str = None) -> list[dict]:
        """Get all trade events (buy/sell/redeem) for a date."""
    
    async def get_errors(self, date: str = None) -> list[dict]:
        """Get all error events across all agents for a date."""
    
    async def get_summary(self, date: str = None) -> dict:
        """
        Quick summary for a date:
        {
            "date": "2026-03-05",
            "total_events": 245,
            "per_agent": {"ceo": 30, "cio": 45, ...},
            "cycles_completed": 48,
            "trades_executed": 3,
            "trades_failed": 1,
            "alerts_raised": 7,
            "errors": 2
        }
        """
    
    async def cleanup_old(self, days_to_keep: int = 7):
        """Delete history older than N days. Run daily."""

STEP 2 — Integrate into BaseAgent (src/agents/base.py):

Add self.history to BaseAgent.__init__:
- Accept history from ctx
- self.history = ctx.get("history")

Add convenience methods to BaseAgent:
    async def log_event(self, event_type: str, data: dict):
        """Log an event to history. Called by all agents."""
        if self.history:
            await self.history.log(self.name, event_type, data)

Wrap on_cycle to auto-log cycle start/end:
    # In the base run loop, around on_cycle:
    await self.log_event("cycle_start", {"cycle_number": n})
    try:
        await self.on_cycle()
        await self.log_event("cycle_end", {"status": "success", "duration_ms": elapsed})
    except Exception as e:
        await self.log_event("error", {"phase": "cycle", "error": str(e)})
        raise

STEP 3 — Add logging to each agent:

CEO (src/agents/ceo.py):
- Log "decision" with full decision JSON (action, market, reasoning, confidence)
- Log "trade_executed" with order result (order_id, price, size, proxy_country)
- Log "trade_failed" with error details
- Log "redeem" with tx_hash and amount

CIO (src/agents/cio.py):
- Log "intel" with trending tokens, sentiments, chart signals
- Log "grok_call" with prompt summary and response
- Log "elfa_call" with endpoint and result count

CSO (src/agents/cso.py):
- Log "opportunity" with market details and score
- Log "scan_results" with markets found, filtered, scored

CPO (src/agents/cpo.py):
- Log "portfolio_check" with positions count, total value, P&L
- Log "alert" with alert_type, symbol, change percentage
- Log "redeemable" with market and amount

CDO (src/agents/cdo.py):
- Log "health_check" with system metrics
- Log "error" with any issues found

Codex (src/agents/codex.py):
- Log "task_received" with task description
- Log "task_completed" with files changed
- Log "task_failed" with error

STEP 4 — Wire into main.py:
- Import AgentHistory
- Initialize: history = AgentHistory(redis_client=bus.redis)
- Add to ctx: ctx["history"] = history

STEP 5 — Telegram commands:
- /history — show today's summary (event counts per agent)
- /history <agent> — show last 10 events for a specific agent
- /trades — show today's trade log

STEP 6 — Also log all pub/sub messages automatically:
In bus.py, add a message logger that records every published message:
- Key: history:bus:{date}
- Logs: channel, publisher, timestamp, payload size
- This gives CGO visibility into inter-agent communication patterns

AFTER BUILDING:
1. Test: python3 -c "from src.core.history import AgentHistory; print('OK')"
2. Restart: docker compose restart orchestrator
3. Wait for one cycle
4. Test /history in Telegram
5. Verify Redis has history keys: docker exec -it redis redis-cli KEYS "history:*"
6. List all files changed
