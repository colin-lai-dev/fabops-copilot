"""Project settings, read from environment variables and `.env` (env vars win).

Every entry point reads configuration through `get_settings()`, so running a module directly
(`uv run python -m fabops.data.seed`) honours `.env` without extra flags.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql://fabops:fabops@localhost:5432/fabops"

    llm_provider: str = "ollama"
    llm_model: str = "qwen3:8b"
    llm_base_url: str | None = None

    anthropic_api_key: SecretStr | None = None
    openai_api_key: SecretStr | None = None
    gemini_api_key: SecretStr | None = None

    fabops_cache_dir: str = ".cache/llm"
    fabops_usage_log: str = ".cache/usage.jsonl"
    fabops_debug_trace: bool = False

    def api_key(self, provider: str) -> str | None:
        secret = {
            "anthropic": self.anthropic_api_key,
            "openai": self.openai_api_key,
            "gemini": self.gemini_api_key,
        }.get(provider)
        return secret.get_secret_value() if secret else None


@lru_cache
def get_settings() -> Settings:
    return Settings()
