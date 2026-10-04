# Author: Yogesh Agrawal
"""Central configuration, loaded from environment / .env.

All services (gateway, agents, MCP clients, PII, observability) read settings
from here so behavior is configurable without code changes.
"""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # App
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    app_env: str = "demo"
    jwt_secret: str = "change-me-demo-secret-not-for-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60

    # Data
    data_dir: str = "/data"
    bank_db: str = "/data/bank.db"
    sessions_db: str = "/data/sessions.db"

    # Ollama / LLM
    ollama_base_url: str = "http://host.docker.internal:11434"
    llm_coordinator: str = "gpt-oss:120b"
    llm_subagent: str = "gpt-oss:120b"
    llm_embed: str = "nomic-embed-text"
    llm_timeout_seconds: int = 120
    thirdparty_llm_enabled: bool = False

    # MCP / mock bank
    mcp_accounts_port: int = 9001
    mcp_transactions_port: int = 9002
    mcp_service_port: int = 9003
    mock_bank_port: int = 9100
    mock_bank_url: str = "http://127.0.0.1:9100"

    # PII
    pii_enabled: bool = True
    pii_spacy_model: str = "en_core_web_sm"

    # Observability
    langfuse_enabled: bool = False
    langfuse_host: str = "http://127.0.0.1:3000"
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""

    # Cost
    cost_per_1k_prompt_tokens: float = 0.0
    cost_per_1k_completion_tokens: float = 0.0
    cost_alert_threshold: float = 100.0

    # Edge
    rate_limit_per_second: int = 4


@lru_cache
def get_settings() -> Settings:
    """Cached singleton settings accessor."""
    return Settings()
