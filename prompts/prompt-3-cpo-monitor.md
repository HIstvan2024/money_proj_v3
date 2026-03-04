Read /docker/money_proj_v3/CLAUDE.md for full project context.
Read /docker/money_proj_v3/skills/cpo.md for monitoring rules.
Read /docker/money_proj_v3/src/agents/cpo.py for the current stub.
Read /docker/money_proj_v3/src/agents/base.py for the BaseAgent interface.
Read /docker/money_proj_v3/src/integrations/polymarket.py for position data.
Read /docker/money_proj_v3/src/integrations/charts.py for price data methods.

TASK: Implement the CPO portfolio monitor in src/agents/cpo.py

THE CPO AGENT MUST:

1. On each 30-min cycle (on_cycle):
   - Fetch all current positions from self.ctx["polymarket"].get_positions()
   - For each position, get the underlying crypto symbol (e.g., BTC UP → BTCUSDT)
   - Fetch chart data: 1h candles for trend, 15m candles for recent moves
   - Calculate: current P&L, 1h change, 4h change
   - Compare against last check (store in Redis or self.state)
   - Alert if any position moved ±10% since last check
   - Alert if any position moved ±15% in 4 hours
   - Publish summary to cpo/alerts channel
   - Use self.think(prompt) to analyze portfolio health via Gemini 3.1 Pro

2. Position tracking state (store in Redis via self.cache):
   - Key: cpo:positions:{market_id}
   - Value: {last_price, last_check_time, entry_price, size, alerts_sent}
   - Update every cycle

3. Alert levels:
   - INFO: Position moved 5-10% → log only
   - WARNING: Position moved 10-15% → publish to cpo/alerts, notify Telegram
   - CRITICAL: Position moved >15% in <4hrs → escalate to CEO, urgent Telegram

4. Crypto UP/DOWN mapping:
   - Parse market question to extract underlying asset
   - "Will BTC be above $100k by March?" → map to BTCUSDT
   - "ETH UP this week?" → map to ETHUSDT
   - Use self.charts.get_price(symbol, interval) for live price
   - Use self.charts.get_price_change(symbol, interval, periods) for % change

5. Portfolio summary format (published to cpo/alerts):
   ```json
   {
     "type": "portfolio_summary",
     "total_positions": 3,
     "total_value": 150.0,
     "total_pnl": 12.5,
     "positions": [...],
     "alerts": [...],
     "timestamp": "..."
   }
   ```

6. On incoming messages (on_message):
   - Listen to ceo/decisions → update position tracking when CEO buys/sells
   - Listen to chart/candle_closed → check if relevant to any position
   - Listen to system/cycle → trigger on_cycle

AFTER BUILDING:
1. Test: python3 -c "from src.agents.cpo import CPOAgent; print('OK')"
2. Restart: docker compose restart orchestrator
3. Check logs: docker logs agent-orchestrator 2>&1 | grep -i "cpo"
4. Test /portfolio in Telegram
5. List all files changed.
