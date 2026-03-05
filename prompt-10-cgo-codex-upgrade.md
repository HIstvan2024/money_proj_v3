Read /docker/money_proj_v3/CLAUDE.md for project context.
Read /docker/money_proj_v3/src/agents/base.py for BaseAgent interface.
Read /docker/money_proj_v3/src/agents/codex.py for the current Codex agent.
Read /docker/money_proj_v3/src/core/llm.py for model assignments.

TASK: Build the CGO (Chief Growth Officer) agent and upgrade Codex with R/W file access.

PART 1 — CODEX UPGRADE: Give it R/W access to the codebase

Currently Codex can only generate code in LLM responses. It needs to actually write files.

Create src/core/codebase.py:

class CodebaseManager:
    """Manages R/W access to the agent source code."""
    
    def __init__(self, project_root="/docker/money_proj_v3"):
        self.root = project_root
    
    def read_file(self, path: str) -> str:
        """Read a source file. Path relative to project root."""
        # e.g., read_file("src/agents/ceo.py")
    
    def write_file(self, path: str, content: str) -> bool:
        """Write content to a file. Creates backup first."""
        # 1. Create backup: {path}.bak.{timestamp}
        # 2. Write new content
        # 3. Return success/failure
    
    def patch_file(self, path: str, old: str, new: str) -> bool:
        """Replace a specific string in a file (like str_replace)."""
        # 1. Verify old string exists exactly once
        # 2. Create backup
        # 3. Replace and write
    
    def list_files(self, directory: str = "src") -> list[str]:
        """List all Python files in a directory."""
    
    def validate_python(self, path: str) -> dict:
        """Syntax-check a Python file. Returns {valid: bool, error: str}."""
        # Use py_compile or ast.parse
    
    def restart_orchestrator(self) -> dict:
        """Rebuild and restart the orchestrator container."""
        # Run: docker compose restart orchestrator
        # Return: {success: bool, logs: str}

Update src/agents/codex.py:
- Add self.codebase = CodebaseManager() in initialization
- Codex can now: read files, write files, patch files, validate, restart
- On task completion, Codex validates syntax before writing
- Creates backups before every change
- Restarts orchestrator after code changes

Update src/core/llm.py — add Codex to model assignments:
- Codex stays on Claude Opus (claude-opus-4-5-20250514)
- CGO gets Gemini 3.1 Pro Preview

PART 2 — CGO (Chief Growth Officer) Agent

Create src/agents/cgo.py:

class CGOAgent(BaseAgent):
    """
    Chief Growth Officer — daily meta-analysis and system improvement.
    
    Runs ONCE PER DAY (not every 30-min cycle).
    Reviews all agent communications, trade outcomes, and system performance.
    Produces improvement tasks for Codex to execute.
    """
    
    name = "cgo"
    # LLM: Gemini 3.1 Pro Preview

DAILY REVIEW PROCESS (on_cycle, but only triggers once per 24h):

1. COLLECT DATA (from Redis):
   - All CEO decisions from last 24h (ceo/decisions history)
   - All CIO intel reports (cio/intel history)
   - All CSO opportunities found (cso/opportunities history)
   - All CPO alerts (cpo/alerts history)
   - All CDO health reports (cdo/health history)
   - Risk manager daily summary
   - Trade history: wins, losses, P&L

2. PERFORMANCE METRICS:
   - Win rate (% of trades that were profitable)
   - Average P&L per trade
   - Best/worst trade
   - Signal accuracy (did CIO intel predict correctly?)
   - Opportunity quality (did CSO find good markets?)
   - Alert accuracy (were CPO alerts actionable?)
   - System uptime and errors
   - Proxy success rate

3. LLM ANALYSIS (Gemini 3.1 Pro):
   Build a comprehensive prompt with ALL collected data and ask:
   - What went well yesterday?
   - What went wrong?
   - Which agent underperformed and why?
   - What patterns do you see in winning vs losing trades?
   - Suggest 3 concrete improvements ranked by impact
   
   Each improvement must be a specific, actionable code change:
   ```json
   {
     "improvements": [
       {
         "priority": 1,
         "agent": "cso",
         "description": "CSO is scoring low-liquidity markets too high",
         "action": "Increase liquidity weight from 25 to 35 in scoring",
         "file": "src/agents/cso.py",
         "estimated_impact": "Fewer bad trades from illiquid markets",
         "risk": "low"
       }
     ]
   }
   ```

4. PUBLISH REPORT:
   - Publish to cgo/daily_report channel
   - Notify Telegram with full daily summary
   - Include: P&L, win rate, metrics, top 3 improvements

5. DELEGATE TO CODEX:
   - For low-risk improvements (config changes, threshold tweaks):
     Auto-submit to codex/tasks channel for immediate execution
   - For medium-risk improvements (logic changes):
     Submit to codex/tasks but require admin /yes confirmation via Telegram
   - For high-risk improvements (architecture changes):
     Report only, do not auto-execute

CODEX RECEIVES CGO TASKS:
- Reads the improvement spec
- Uses self.codebase to read the target file
- Generates the fix using Claude Opus
- Validates syntax
- If low-risk: writes directly, restarts orchestrator
- If medium-risk: writes to a staging area, notifies admin for approval
- After execution: publishes result to codex/results
- Notifies Telegram: "Applied improvement: [description]"

Create skills/cgo.md:
- Document the daily review process
- Define performance metrics
- Define risk levels for improvements
- Define the CGO → Codex pipeline

PART 3 — WIRE EVERYTHING:

1. Add CGO to src/core/llm.py:
   "cgo": {"provider": "gemini", "model": "gemini-3.1-pro-preview"}

2. Add to src/main.py:
   - Import CGOAgent
   - Initialize and add to agents list
   - Pass codebase manager to ctx

3. Add Redis history tracking:
   - Each agent should store its last 24h of messages in Redis lists
   - Key pattern: history:{channel}:{date}
   - Capped at 1000 entries per day
   - CGO reads these for daily analysis

4. Add Telegram commands:
   - /daily — show latest CGO daily report
   - /improvements — show pending improvement tasks
   - /approve <id> — approve a medium-risk improvement

5. Add scheduler support:
   - CGO cycle runs at 00:00 UTC daily (not every 30 min)
   - Add a daily_cycle trigger to scheduler.py

AFTER BUILDING:
1. Test all imports
2. Restart orchestrator
3. Force a CGO daily review: publish a test trigger
4. Check Telegram for the daily report
5. Verify Codex can read/write files via CodebaseManager
6. List ALL files changed
