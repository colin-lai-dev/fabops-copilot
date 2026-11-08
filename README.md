# FabOps Copilot

An anomaly-handling assistant for **Fab-X, a fictional fab**: permission-aware RAG over SOPs and
past incident reports, plus a triage agent that queries read-only MES tools and proposes actions
that a human must approve. All data is synthetic.

> Status: Phase 0 (foundation). See [docs/PLAN.md](docs/PLAN.md).

## Quick start

Requirements: Docker Desktop, [uv](https://docs.astral.sh/uv/), and (optional) Ollama.

```bash
cp .env.example .env
docker compose up -d        # Postgres + pgvector
uv sync
make seed                   # load schema + synthetic data
make test
```

Synthetic data is already generated under `data/generated/`. To regenerate it from rules:
`make generate`. To rewrite document prose with a local model (optional): `make polish`.

## Design decisions

Architecture decisions are recorded in [docs/decisions/](docs/decisions/).
