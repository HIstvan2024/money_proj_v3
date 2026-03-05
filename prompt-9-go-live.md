Read /docker/money_proj_v3/CLAUDE.md for project context.

TASK: Verify the system is ready and enable autonomous trading.

PRE-FLIGHT CHECKLIST — verify each one and report pass/fail:

1. AGENTS RUNNING: docker logs agent-orchestrator 2>&1 | grep "started" — all 7 agents?
2. REDIS CONNECTED: docker logs agent-orchestrator 2>&1 | grep -i "redis" — no errors?
3. TELEGRAM WORKING: docker logs agent-orchestrator 2>&1 | grep -i "telegram.enabled" — once only?
4. CHARTS STREAMING: docker logs agent-orchestrator 2>&1 | grep -i "btcusdt" — data flowing?
5. ELFA API: docker logs agent-orchestrator 2>&1 | grep -i "elfa" — connected?
6. PROXY WORKING: confirmed by test trade earlier
7. WALLET: confirmed by test trade earlier
8. RISK LIMITS SET: docker exec agent-orchestrator python3 -c "from src.core.config import Settings; s=Settings(); print(f'Max pos: ${s.risk_max_position_size}, Max exposure: ${s.risk_max_total_exposure}, Daily loss limit: ${s.risk_daily_loss_limit}')"

IF ALL PASS:
1. Verify the scheduler is triggering 30-min cycles:
   docker logs agent-orchestrator 2>&1 | grep -i "cycle"
   
2. Force one live cycle and monitor:
   - Publish a cycle trigger to Redis
   - Watch logs in real-time: docker logs -f agent-orchestrator 2>&1 | grep -E "cio|cso|ceo|cpo|risk"
   - Wait for the full pipeline to complete
   - Check Telegram for notifications

3. If the cycle completes successfully (even if CEO decides SKIP/HOLD):
   - System is live
   - Report: "SYSTEM IS LIVE — autonomous trading enabled"
   - Show: next cycle time, risk limits, active positions

IF ANY CHECK FAILS:
- Fix the issue
- Restart and re-check
- Do not enable autonomous trading until all checks pass

Report the full pre-flight results.
