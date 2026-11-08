.PHONY: up down install lint fmt test test-db generate polish seed

up:
	docker compose up -d

down:
	docker compose down

install:
	uv sync

lint:
	uv run ruff check .
	uv run ruff format --check .

fmt:
	uv run ruff check --fix .
	uv run ruff format .

test:
	uv run pytest

# DB targets load .env so DATABASE_URL (and a non-default FABOPS_DB_PORT) is honoured.
test-db:
	uv run --env-file .env pytest -m db

# Regenerate synthetic data from rules (no LLM). Output is committed under data/generated/.
generate:
	uv run python -m fabops.data.generate

# Optional: rewrite document prose with local Ollama (ADR-0004), then verify facts.
polish:
	uv run python -m fabops.data.polish

# Load schema and generated data into Postgres.
seed:
	uv run --env-file .env python -m fabops.data.seed
