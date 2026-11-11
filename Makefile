.PHONY: up down install lint fmt test test-db generate polish seed index eval-dev eval-test mcp api web web-build

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

test-db:
	uv run pytest -m db

# Regenerate synthetic data from rules (no LLM). Output is committed under data/generated/.
generate:
	uv run python -m fabops.data.generate

# Optional: rewrite document prose with local Ollama (ADR-0004), then verify facts.
polish:
	uv run python -m fabops.data.polish

# Load schema and generated data into Postgres.
seed:
	uv run python -m fabops.data.seed

# Chunk, embed (bge-m3 dense+sparse, CPU) and store in chunks. Run after seed.
index:
	uv run python -m fabops.rag.index

# Eval (ADR-0005). SYSTEM selects the system under test (see evals/systems.py).
SYSTEM ?= refuse_all

eval-dev:
	uv run python -m evals.run --split dev --system $(SYSTEM)

# Test split: only at a gate, with Colin's approval (CLAUDE.md, "Eval 規則").
eval-test:
	uv run python -m evals.run --split test --system $(SYSTEM) --allow-test

# Phase 2: read-only MES tools over MCP (needs FABOPS_JWT_SECRET), API + UI, frontend dev server.
mcp:
	uv run python -m fabops.mcp_server.server

api:
	uv run python -m fabops.api.app

web-build:
	cd web && npm install && npm run build

web:
	cd web && npm run dev
