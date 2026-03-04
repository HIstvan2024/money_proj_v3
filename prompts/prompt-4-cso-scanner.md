Read /docker/money_proj_v3/CLAUDE.md for full project context.
Read /docker/money_proj_v3/skills/cso.md for market scanning rules.
Read /docker/money_proj_v3/src/agents/cso.py for the current stub.
Read /docker/money_proj_v3/src/agents/base.py for the BaseAgent interface.
Read /docker/money_proj_v3/src/integrations/polymarket.py for market data methods.

TASK: Implement the CSO market scanner in src/agents/cso.py

THE CSO AGENT MUST:

1. On each 30-min cycle (on_cycle):
   - Query Polymarket for crypto-related UP/DOWN markets
   - Filter for: active markets, sufficient liquidity, reasonable expiry
   - Score each opportunity based on: spread, volume, time to expiry, price
   - Cross-reference with CIO intel (trending tokens from Elfa/Grok)
   - Use self.think(prompt) → Gemini 3.1 Pro to rank opportunities
   - Publish top opportunities to cso/opportunities channel
   - Notify Telegram if high-scoring opportunity found

2. Market discovery:
   - Use Gamma API: https://gamma-api.polymarket.com
   - Endpoint: /markets — search for crypto UP/DOWN markets
   - Filter params: active=true, closed=false
   - Search terms: "BTC", "ETH", "SOL", "XRP", "crypto", "bitcoin", "ethereum"
   - Focus on binary YES/NO markets about price movements

3. Opportunity scoring (0-100):
   - Liquidity score (0-25): orderbook depth, daily volume
   - Spread score (0-25): tighter spread = better
   - Value score (0-25): price vs CIO intel alignment
   - Time score (0-25): optimal window (not too close to expiry, not too far)
   
   Only publish opportunities scoring > 60

4. Output format (published to cso/opportunities):
   ```json
   {
     "type": "opportunity",
     "market_id": "...",
     "question": "Will BTC be above $100k by March 15?",
     "token_id": "...",
     "outcome": "Yes",
     "current_price": 0.65,
     "score": 78,
     "scores": {"liquidity": 20, "spread": 22, "value": 18, "time": 18},
     "volume_24h": 50000,
     "spread": 0.02,
     "expiry": "2026-03-15",
     "reasoning": "...",
     "timestamp": "..."
   }
   ```

5. On incoming messages (on_message):
   - Listen to cio/intel → use trending tokens to refine search
   - Listen to ceo/decisions → track which markets CEO already entered
   - Listen to system/cycle → trigger on_cycle

6. Rate limiting:
   - Cache market list for 5 minutes (avoid hammering Gamma API)
   - Cache individual market details for 2 minutes
   - Use self.cache for all caching

AFTER BUILDING:
1. Test: python3 -c "from src.agents.cso import CSOAgent; print('OK')"
2. Restart: docker compose restart orchestrator
3. Check logs: docker logs agent-orchestrator 2>&1 | grep -i "cso"
4. List all files changed.
