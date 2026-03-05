Read /docker/money_proj_v3/CLAUDE.md for project context.
Read /docker/money_proj_v3/src/agents/base.py for BaseAgent interface.
Read /docker/money_proj_v3/src/core/cache.py for Redis cache.

TASK: Add working memory to each agent — a compact, rolling journal that makes agents smarter each cycle without bloating LLM prompts.

This is NOT raw logging (that's history.py). This is curated context — each agent writes a 3-5 line summary after every cycle, and reads it at the start of the next cycle as part of its system prompt.

STEP 1 — Create src/core/memory.py:

class AgentMemory:
    """
    Per-agent working memory — rolling journal entries stored in Redis.
    
    Each agent writes a short journal entry after each cycle.
    Next cycle, the last N entries are injected into the LLM system prompt.
    This gives agents continuity without overwhelming them.
    
    Key: memory:{agent}
    Value: Redis list of JSON entries, newest first
    Max entries: 7 (rolling window = ~3.5 hours of 30-min cycles)
    """
    
    def __init__(self, redis_client):
        self.redis = redis_client
        self.max_entries = 7
    
    async def remember(self, agent: str, entry: str):
        """
        Store a journal entry (max 200 words).
        Auto-trims to max_entries.
        Entry format stored: {"text": "...", "timestamp": "...", "cycle": N}
        """
    
    async def recall(self, agent: str) -> str:
        """
        Get all journal entries as a single string for LLM context.
        Returns formatted text like:
        
        === YOUR RECENT MEMORY ===
        [Cycle 48, 14:30 UTC] Bought BTC YES at $0.62, high confidence from CIO bullish signal.
        [Cycle 47, 14:00 UTC] Skipped ETH market — spread too wide (12%). CSO score only 55.
        [Cycle 46, 13:30 UTC] Sold SOL position at $0.71, +14% gain. CIO turned bearish.
        ===
        
        Returns empty string if no memories exist.
        """
    
    async def clear(self, agent: str):
        """Clear an agent's memory (useful for fresh start)."""

STEP 2 — Integrate into BaseAgent (src/agents/base.py):

Add to __init__:
    self.memory = ctx.get("memory")

Add convenience methods:
    async def remember(self, entry: str):
        """Write a journal entry after this cycle."""
        if self.memory:
            await self.memory.remember(self.name, entry)
    
    async def recall(self) -> str:
        """Get recent memory for LLM context."""
        if self.memory:
            return await self.memory.recall(self.name)
        return ""

Update the think() method to auto-inject memory:
    async def think(self, prompt: str, system_prompt: str = "", **kwargs) -> str | None:
        # Get memory context
        memory_context = await self.recall()
        
        # Prepend memory to system prompt if available
        if memory_context and system_prompt:
            system_prompt = memory_context + "\n\n" + system_prompt
        elif memory_context:
            system_prompt = memory_context
        
        # Rest of existing think() logic...

STEP 3 — Wire into main.py:
    from src.core.memory import AgentMemory
    memory = AgentMemory(redis_client=bus.redis)
    ctx["memory"] = memory

STEP 4 — Add journal writing to each agent at the END of on_cycle():

CEO (src/agents/ceo.py) — max 200 words, focus on:
- What decision was made and why
- Trade outcomes (filled/rejected/skipped)
- Risk limit status (headroom remaining)
- Markets deliberately skipped and reason

Example entry:
"Cycle 48: BUY BTC YES at $0.65, confidence 82%. CIO bullish (Elfa mentions up 40%, Grok agrees). Risk OK: $15 exposure added, $35 headroom left. Skipped ETH market — spread 11% too wide."

CIO (src/agents/cio.py) — max 150 words, focus on:
- Sentiment direction changes (was bullish, now neutral)
- Which signals were new vs repeated
- Data source reliability (Elfa worked, Grok timed out)

Example entry:
"Cycle 48: BTC sentiment shifting bullish→strong bullish. Elfa mentions +40% vs last cycle. Grok confirms via X volume spike. ETH flat, no change. SOL bearish — 3 negative news articles. Elfa narratives endpoint still down."

CSO (src/agents/cso.py) — max 100 words, focus on:
- Best opportunities found and scores
- Markets already sent to CEO (avoid resurfacing)
- Liquidity changes noticed

Example entry:
"Cycle 48: Found 5 markets above threshold. Best: BTC $100k March (score 82). Already sent ETH $3k to CEO last cycle — rejected for low liquidity. SOL markets drying up, volume down 30%."

CPO (src/agents/cpo.py) — max 100 words, focus on:
- Position movements since last check
- Which alerts were raised
- Approaching thresholds

Example entry:
"Cycle 48: 6 positions, +$9.24 total P&L. BTC YES up 5% (no alert). Iran ceasefire approaching 15% threshold — may alert next cycle. No redeemable positions found."

CDO — No journal needed (raw health checks are fine)
Codex — No journal needed (task-based, not cyclic)
Assistant — No journal needed

STEP 5 — LLM-generated journal entries:
Instead of hardcoding what to write, let each agent use its LLM to compress the cycle:

At the end of on_cycle(), each agent calls:
    # Build summary of what happened this cycle
    summary_prompt = f"""
    Summarize this cycle in 3-5 lines for your future self. Focus only on:
    {agent_specific_focus_instructions}
    
    This cycle's data:
    {cycle_results_json}
    
    Write in first person, be specific with numbers. Max 200 words.
    """
    journal = await self.think(summary_prompt)
    if journal:
        await self.remember(journal)

STEP 6 — Telegram commands:
- /memory — show all agents' latest journal entries
- /memory <agent> — show specific agent's full memory (all 7 entries)
- /memory clear <agent> — clear an agent's memory

STEP 7 — Memory stats in /status:
Add to /status output: "Memory: CEO 7/7, CIO 5/7, CSO 3/7" showing how many entries each agent has.

AFTER BUILDING:
1. Test: python3 -c "from src.core.memory import AgentMemory; print('OK')"
2. Restart: docker compose restart orchestrator
3. Wait for 2-3 cycles
4. Test /memory in Telegram — should see journal entries
5. Check that LLM prompts are getting memory context (add a debug log in think())
6. List all files changed
