Read /docker/money_proj_v3/CLAUDE.md for project context.
Read /docker/money_proj_v3/src/core/config.py for settings.
Read /docker/money_proj_v3/src/agents/ceo.py for the decision engine.
Read /docker/money_proj_v3/src/integrations/polymarket.py for the client.

TASK: Build a risk management layer that the CEO enforces before every trade.

STEP 1 — Add risk settings to src/core/config.py:
    # Risk Limits
    risk_max_position_size: float = 10.0       # Max $10 per single position
    risk_max_total_exposure: float = 50.0      # Max $50 total across all positions
    risk_daily_loss_limit: float = 20.0        # Stop trading if $20 lost today
    risk_max_positions: int = 5                # Max 5 simultaneous positions
    risk_min_confidence: float = 0.7           # CEO must be >70% confident
    risk_min_liquidity: float = 1000.0         # Min $1000 24h volume on market
    risk_max_spread: float = 0.10              # Max 10% spread
    risk_cooldown_after_loss: int = 60         # Wait 60 min after a losing trade

STEP 2 — Create src/core/risk.py:

class RiskManager:
    """Enforces risk limits before every trade. CEO cannot bypass."""
    
    def __init__(self, settings, cache, polymarket_client):
        # Load limits from settings
        # Track daily P&L in Redis
    
    async def check_trade(self, trade: dict) -> dict:
        """
        Validate a proposed trade against all risk limits.
        Returns: {"approved": bool, "reason": str, "violations": [...]}
        
        Checks (ALL must pass):
        1. Position size <= risk_max_position_size
        2. Total exposure (existing + new) <= risk_max_total_exposure
        3. Daily P&L not below -risk_daily_loss_limit
        4. Active positions count < risk_max_positions
        5. CEO confidence >= risk_min_confidence
        6. Market liquidity >= risk_min_liquidity
        7. Market spread <= risk_max_spread
        8. Not in cooldown after a loss
        """
    
    async def record_trade(self, trade_result: dict):
        """Record completed trade for daily P&L tracking."""
        # Store in Redis: risk:daily_pnl:{date}
        # Store in Redis: risk:trades:{date}
        # Store in Redis: risk:last_loss_time (for cooldown)
    
    async def get_daily_summary(self) -> dict:
        """Return today's trading summary."""
        # Returns: {trades_count, wins, losses, daily_pnl, exposure, headroom}
    
    async def reset_daily(self):
        """Called at midnight UTC to reset daily counters."""

STEP 3 — Wire into CEO (src/agents/ceo.py):
- Import RiskManager
- Before EVERY trade execution, call risk_manager.check_trade()
- If not approved, skip the trade and log the reason
- After every trade, call risk_manager.record_trade()
- Add risk summary to the CEO's cycle report

STEP 4 — Wire into main.py:
- Initialize RiskManager with settings, cache, polymarket
- Add to ctx dict
- CEO accesses via self.ctx["risk"]

STEP 5 — Telegram commands:
- Update /status to show: daily P&L, exposure, headroom, trade count
- Add /risk command: shows all current risk limits and today's stats
- Add /risk set <param> <value>: let admin change limits live (store in Redis, override config)

STEP 6 — Environment variables (add to docker-compose.yml):
- RISK_MAX_POSITION_SIZE=${RISK_MAX_POSITION_SIZE:-10}
- RISK_MAX_TOTAL_EXPOSURE=${RISK_MAX_TOTAL_EXPOSURE:-50}
- RISK_DAILY_LOSS_LIMIT=${RISK_DAILY_LOSS_LIMIT:-20}
- RISK_MAX_POSITIONS=${RISK_MAX_POSITIONS:-5}

CRITICAL: The RiskManager is a HARD GATE. Even if the CEO LLM says "BUY with 99% confidence", if risk limits are violated, the trade DOES NOT execute. Log the override and notify Telegram.

AFTER BUILDING:
1. Test: python3 -c "from src.core.risk import RiskManager; print('OK')"
2. Restart: docker compose restart orchestrator
3. Test /risk in Telegram
4. List all files changed
