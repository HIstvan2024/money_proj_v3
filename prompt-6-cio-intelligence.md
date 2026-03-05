Read /docker/money_proj_v3/CLAUDE.md for project context.
Read /docker/money_proj_v3/src/agents/cio.py for the current stub.
Read /docker/money_proj_v3/src/agents/base.py for BaseAgent interface.
Read /docker/money_proj_v3/src/integrations/elfa.py for Elfa AI client.
Read /docker/money_proj_v3/src/integrations/charts.py for chart data.
Read /docker/money_proj_v3/src/core/llm.py for LLM routing (CIO uses gemini-3-flash + Grok).

TASK: Implement the CIO intelligence engine in src/agents/cio.py

THE CIO AGENT:
- Main LLM: Gemini 3 Flash (fast analysis via self.think())
- Secondary: Grok via self.llm.grok() for X/Twitter sentiment (in Python only)
- Data: Elfa AI for trending tokens + social mentions, Binance charts for price moves

ON EACH 30-MIN CYCLE (on_cycle):

1. Gather data from all sources:
   a. Elfa trending tokens (1h window): await self.elfa.get_trending_tokens()
   b. Elfa trending narratives: await self.elfa.get_trending_narratives()
   c. For top 5 trending tokens, get keyword mentions: await self.elfa.get_keyword_mentions(token)
   d. For top 5 trending tokens, get token news: await self.elfa.get_token_news(token)
   e. Chart signals: check all tracked pairs for >3% moves via self.charts

2. Grok sentiment analysis (for top 3 tokens only — rate limit aware):
   - Build prompt with token name + recent mentions + price action
   - Call await self.llm.grok(prompt, system_prompt) 
   - System prompt: "You are a crypto sentiment analyst. Analyze X/Twitter sentiment for this token. Rate: BULLISH / BEARISH / NEUTRAL with confidence 0-1. Be concise."
   - Parse response

3. Synthesize with Gemini 3 Flash:
   - Build context prompt combining: Elfa data, Grok sentiment, chart signals
   - Call await self.think(prompt) for overall market analysis
   - Output structured intel report

4. Publish to cio/intel:
   ```json
   {
     "type": "cycle_report",
     "timestamp": "...",
     "trending_tokens": [{"name": "BTC", "mentions": 500, "sentiment": "BULLISH", "confidence": 0.8}],
     "narratives": ["crypto regulation", "ETF flows"],
     "chart_signals": [{"symbol": "BTCUSDT", "change_1h": 2.5, "direction": "up"}],
     "grok_sentiments": [{"token": "BTC", "sentiment": "BULLISH", "confidence": 0.85, "summary": "..."}],
     "overall_assessment": "Market bullish, BTC leading with strong social momentum",
     "recommended_tokens": ["BTC", "ETH"],
     "avoid_tokens": ["XRP"]
   }
   ```

5. Notify Telegram with a concise summary

ON INCOMING MESSAGES (on_message):

1. cso/opportunities → Deep research the specific token:
   - Get Elfa mentions + news for that token
   - Get Grok sentiment for that token
   - Publish targeted research to cio/intel with type "opportunity_research"

2. cpo/alerts → Investigate price movement:
   - Check if movement aligns with social sentiment
   - Get latest news via Elfa
   - Publish to cio/intel with type "movement_investigation"

3. chart/candle_closed → Check for significant moves:
   - If >3% move on any candle close, investigate
   - Cross-reference with Elfa mentions spike
   - Publish to cio/intel with type "chart_signal"

ERROR HANDLING:
- If Elfa API fails, continue with chart data + Grok only
- If Grok fails, continue with Elfa + charts only
- Always produce a report even with partial data — note which sources were unavailable
- Cache aggressively to avoid rate limits

AFTER BUILDING:
1. Test: python3 -c "from src.agents.cio import CIOAgent; print('OK')"
2. Restart: docker compose restart orchestrator
3. Check logs: docker logs agent-orchestrator 2>&1 | grep -i "cio" | tail -20
4. Wait for first cycle and check Telegram for intel report
5. List all files changed
