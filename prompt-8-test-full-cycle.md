Read /docker/money_proj_v3/CLAUDE.md for project context.
Read /docker/money_proj_v3/src/agents/ceo.py
Read /docker/money_proj_v3/src/agents/cio.py
Read /docker/money_proj_v3/src/agents/cso.py
Read /docker/money_proj_v3/src/agents/cpo.py
Read /docker/money_proj_v3/src/core/risk.py

TASK: Run one full 30-minute analysis cycle manually and show every step.

Create /docker/money_proj_v3/test_full_cycle.py:

This script simulates the exact same cycle the orchestrator runs every 30 minutes,
but step by step with full logging so we can verify the pipeline.

```
Step 1 — CIO Intelligence Gathering
- Call Elfa trending tokens
- Call Elfa narratives  
- Get Grok sentiment for top 3 tokens
- Get chart signals from Binance
- Print full intel report

Step 2 — CSO Market Scanning
- Search Polymarket for crypto UP/DOWN markets
- Score each opportunity
- Print top 5 with scores

Step 3 — CEO Decision Making
- Feed CIO intel + CSO opportunities + current positions to CEO
- Get LLM decision (Gemini 3.1 Pro)
- Print the raw decision JSON
- Run through RiskManager.check_trade()
- Print approval/rejection with reasons

Step 4 — Trade Execution (DRY RUN)
- If CEO approved a trade, print what WOULD execute but DO NOT place real orders
- Print: market, side, size, price, proxy country

Step 5 — CPO Portfolio Check
- Fetch current positions
- Check for alerts (moves, resolved markets, redeemable)
- Print portfolio summary

Step 6 — Summary
- Print full pipeline results
- Note any errors or missing data
- Recommend if system is ready to go live
```

Run it: cd /docker/money_proj_v3 && PYTHONPATH=/docker/money_proj_v3 python3 test_full_cycle.py

Show me the FULL output. Do not summarize — I need to see every step.
If anything fails, debug and fix it, then rerun.
