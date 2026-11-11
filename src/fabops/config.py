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
    llm_reasoning_effort: str | None = None  # "none" disables qwen3 thinking on Ollama

    anthropic_api_key: SecretStr | None = None
    openai_api_key: SecretStr | None = None
    gemini_api_key: SecretStr | None = None

    # Retrieval models (ADR-0008: CPU is fine on an 8 GB GPU shared with the LLM).
    embed_model: str = "BAAI/bge-m3"
    rerank_model: str = "BAAI/bge-reranker-v2-m3"
    embed_device: str = "cpu"

    fabops_cache_dir: str = ".cache/llm"
    fabops_usage_log: str = ".cache/usage.jsonl"
    fabops_debug_trace: bool = False

    # Agent tools (ADR-0001): the API signs short-lived identity tokens, the MCP server verifies.
    fabops_jwt_secret: SecretStr | None = None
    fabops_mcp_url: str = "http://127.0.0.1:8765/mcp"

    # Langfuse export of masked traces (ADR-0007). Off unless FABOPS_LANGFUSE=1 and keys are set.
    fabops_langfuse: bool = False
    langfuse_public_key: SecretStr | None = None
    langfuse_secret_key: SecretStr | None = None
    langfuse_host: str = "https://cloud.langfuse.com"

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
