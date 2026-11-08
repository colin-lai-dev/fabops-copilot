from fabops.config import Settings


def test_env_file_is_read_and_env_vars_win(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text(
        "DATABASE_URL=postgresql://u:p@localhost:5433/db\nLLM_MODEL=from-file\n"
        "OPENAI_API_KEY=sk-test\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("LLM_MODEL", "from-env")
    s = Settings(_env_file=env)
    assert s.database_url.endswith(":5433/db")
    assert s.llm_model == "from-env"
    assert s.api_key("openai") == "sk-test"
    assert s.api_key("ollama") is None
    assert "sk-test" not in repr(s)
