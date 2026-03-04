"""Settings loaded from .env file."""
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Redis
    redis_host: str = "redis"
    redis_port: int = 6379
    redis_password: str = ""

    # Anthropic
    anthropic_api_key: str = ""

    # Google Gemini
    gemini_api_key: str = ""

    # xAI / Grok
    xai_api_key: str = ""
    xai_base_url: str = "https://api.x.ai/v1"

    # Elfa AI
    elfa_api_key: str = ""

    # Telegram
    tg_bot_token: str = ""
    tg_admin_chat_id: str = ""

    # Charts (Binance — no key needed)
    chart_pairs: str = "BTCUSDT,ETHUSDT,SOLUSDT,XRPUSDT"
    chart_intervals: str = "15m,1h"

    # Polymarket
    poly_wallet_private_key: str = ""
    poly_wallet_address: str = ""
    poly_chain_id: int = 137
    poly_proxy_url: str = ""              # IPRoyal: http://user:pass@host:port
    poly_rpc_url: str = ""                # Chainstack Polygon RPC

    # OpenRouter (optional)
    openrouter_api_key: str = ""

    # n8n
    n8n_webhook_url: str = "http://n8n-n8n-1:5678"

    # Agent config
    analysis_interval: int = 30  # minutes
    log_level: str = "INFO"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
