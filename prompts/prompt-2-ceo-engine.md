Read /docker/money_proj_v3/CLAUDE.md for full project context.
Read /docker/money_proj_v3/skills/ceo.md for the CEO decision matrix.
Read /docker/money_proj_v3/src/agents/ceo.py for the current stub.
Read /docker/money_proj_v3/src/agents/base.py for the BaseAgent interface.
Read /docker/money_proj_v3/src/core/llm.py for how LLM routing works.
Read /docker/money_proj_v3/src/integrations/polymarket.py for available methods.

TASK: Implement the CEO decision engine in src/agents/ceo.py

THE CEO AGENT MUST:

1. On each 30-min cycle (on_cycle):
   - Gather intel from CIO (latest from Redis key or channel)
   - Get current positions from PolymarketClient via self.ctx["polymarket"]
   - Get opportunities from CSO (latest from Redis)
   - Get chart data from self.charts
   - Build a context prompt with ALL this data
   - Call self.think(prompt) → Gemini 3.1 Pro reasons over everything
   - Parse the LLM response into a structured decision
   - Execute the decision (buy/sell/hold)
   - Publish decision to ceo/decisions channel
   - Notify admin via Telegram

2. On incoming messages (on_message):
   - Listen to cio/intel → store latest intel
   - Listen to cso/opportunities → evaluate immediately if high confidence
   - Listen to cpo/alerts → handle escalations (±15% moves)
   - Listen to system/cycle → trigger on_cycle

3. Decision logic (give this to the LLM as system prompt):
   
   DECISION MATRIX:
   | Condition | Action |
   |-----------|--------|
   | Positive intel + new opportunity + no existing position | BUY |
   | Positive intel + existing position profitable | HOLD |
   | Negative intel + existing position | SELL |
   | Mixed signals | HOLD + monitor |
   | Position ±15% in <4hrs | ESCALATE — deep review |
   | No clear signal | SKIP |
   
   CONSTRAINTS:
   - Maximum position size: configurable (start with $50)
   - Never go all-in on one market
   - Always provide reasoning
   - Confidence threshold: only act if confidence > 0.7

4. Trade execution:
   - Use execute_with_proxy_rotation from src.integrations.proxy
   - Use self.ctx["polymarket"].place_order()
   - Log every trade with full reasoning
   - Notify via Telegram before AND after execution

5. Expected LLM response format (instruct Gemini to use this):
   ```json
   {
     "action": "buy|sell|hold|skip",
     "market_id": "...",
     "token_id": "...",
     "size": 0.0,
     "price": 0.0,
     "confidence": 0.0,
     "reasoning": "...",
     "risk_factors": ["..."]
   }
   ```

AFTER BUILDING:
1. Test imports: python3 -c "from src.agents.ceo import CEOAgent; print('OK')"
2. Restart: docker compose restart orchestrator
3. Check logs: docker logs agent-orchestrator --tail 30
4. List all files changed.

Do NOT modify other agents. Focus only on CEO.
