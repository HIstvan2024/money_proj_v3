Read /docker/money_proj_v3/CLAUDE.md for full project context.
Read /docker/money_proj_v3/src/integrations/proxy.py to understand the ProxyManager.
Read /docker/money_proj_v3/src/core/config.py for available settings.
Read /docker/money_proj_v3/src/agents/base.py for the BaseAgent interface.

TASK: Build src/integrations/polymarket.py — the Polymarket CLOB client.

REQUIREMENTS:
- The user has ACTIVE positions on Polymarket that need to be read
- Auth is wallet-only: POLY_WALLET_PRIVATE_KEY + POLY_WALLET_ADDRESS
- No POLY_API_KEY/SECRET/PASSPHRASE — those don't exist
- Proxy: POLY_PROXY_URL in HOST:PORT:USER:PASS format (IPRoyal residential)
- RPC: POLY_RPC_URL is a Chainstack Polygon node
- Chain: Polygon (chain_id 137)

INVESTIGATE FIRST:
1. pip show py-clob-client — check version and location
2. python3 -c "from py_clob_client.client import ClobClient; print(dir(ClobClient))" — see available methods
3. python3 -c "from py_clob_client.client import ClobClient; help(ClobClient.__init__)" — check constructor args
4. Check if py-clob-client supports proxy parameter
5. If py-clob-client doesn't support proxy natively, we'll use aiohttp with proxy for REST calls

BUILD THE CLIENT WITH THESE CAPABILITIES:

class PolymarketClient:
    """Async Polymarket CLOB client with proxy rotation."""
    
    Core methods needed:
    
    1. get_positions(wallet_address) -> list[dict]
       - Fetch all current positions for the wallet
       - Return: market_id, token_id, size, avg_price, current_price, pnl
       
    2. get_market(market_id) -> dict
       - Fetch market details: question, outcomes, prices, volume, end_date
       - Focus on crypto UP/DOWN markets
       
    3. get_orderbook(token_id) -> dict
       - Fetch current orderbook: bids, asks, spread, midpoint
       
    4. place_order(token_id, side, price, size) -> dict
       - Place a limit order via CLOB
       - Must use proxy rotation (from ProxyManager)
       - Must use wallet signing
       - Return: order_id, status
       
    5. cancel_order(order_id) -> bool
       - Cancel an existing order
       
    6. get_open_orders() -> list[dict]
       - Fetch all open/pending orders

    All methods should:
    - Use the proxy manager for requests (import from src.integrations.proxy)
    - Use POLY_RPC_URL for any on-chain calls
    - Cache results via self.cache where appropriate
    - Log with structlog
    - Handle errors gracefully

AFTER BUILDING THE CLIENT:

1. Wire it into src/main.py:
   - Import PolymarketClient
   - Initialize with settings (wallet, proxy, rpc)
   - Add to ctx dict so all agents can access it

2. Add a /portfolio command to telegram.py:
   - Show current positions with market name, size, avg price, current price, P&L
   - Format nicely with emojis

3. Update the /status command to include position count

4. Test: python3 -c "from src.integrations.polymarket import PolymarketClient; print('OK')"

5. Restart: docker compose restart orchestrator

6. List all files you changed.

IMPORTANT: The Polymarket CLOB API base URL is https://clob.polymarket.com
Gamma API for market data: https://gamma-api.polymarket.com
Use aiohttp for async HTTP calls. The py-clob-client is sync — wrap it or rewrite as async.
