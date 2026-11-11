"""Run the agent-tool leak cases at the tool level (PLAN Phase 2; no LLM, no cost).

Each case: sign a token for the asker, call the tool through the FastMCP server in-process
(HTTP + JWT verifier, ADR-0001), and look for `target_ids` / `forbidden_strings` in the
result. Agent-level runs (the LLM asks the question) live with the agent eval.

Systems:
- `tools`: production — Postgres store with the scope filter, retriever pre-filter, tool exit check.
- `tools-unfiltered`: control — no MES filter, no retrieval pre-filter, no exit check
  (`evals/baselines.py`); shows the test detects a leak.
- `tools-jsonl`: CI — the MES tool cases only, on the in-memory JSONL store (no Postgres, no
  retrieval models, no LLM). `--fail-on-leak` exits 1 if any case leaks.

    uv run python -m evals.leak_tools --system tools
    uv run python -m evals.leak_tools --system tools-unfiltered
"""

from __future__ import annotations

import argparse
import asyncio
import json
import secrets
import sys
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from evals.leak import contains_any
from evals.run import RESULTS, files_sha256, git_state
from evals.schema import ToolLeakCase, load_tool_leak_cases

ROOT = Path(__file__).resolve().parents[1]
TOOL_CASES = ROOT / "evals" / "leak_tool_cases.jsonl"
SYSTEMS = ("tools", "tools-unfiltered", "tools-jsonl")
MES_TOOLS = ("get_lot_history", "get_equipment_status", "get_dispatch_log")


@dataclass
class ToolLeakResult:
    cid: str
    boundary: str
    tool: str
    asker_user_id: str
    leaked: bool
    matched: list[str]
    found: bool | None
    error: str | None = None


def build_tools(system: str):
    """MesTools for a system name (lazy imports: needs Postgres and the retrieval models)."""
    import psycopg

    from evals.systems import make_retriever
    from fabops.authz.trace import Tracer
    from fabops.config import get_settings
    from fabops.mcp_server.store import PgMesStore
    from fabops.mcp_server.tools import MesTools

    url = get_settings().database_url

    def connect():
        return psycopg.connect(url)

    if system == "tools":
        return MesTools(PgMesStore(connect), make_retriever(), Tracer.from_env())
    if system == "tools-jsonl":
        from fabops.mcp_server.store import JsonlMesStore

        return MesTools(
            JsonlMesStore(),
            None,
            Tracer(Path(get_settings().fabops_cache_dir).parent / "traces.jsonl"),
        )
    if system == "tools-unfiltered":
        from evals.baselines import UnfilteredMesStore

        cache = Path(get_settings().fabops_cache_dir).parent
        return MesTools(
            UnfilteredMesStore(connect),
            make_retriever(unfiltered=True),
            Tracer(cache / "traces-unmasked.jsonl", unsafe_unmasked=True),
            exit_checks=False,
        )
    raise ValueError(f"unknown system {system!r}; choose from {SYSTEMS}")


def judge(case: ToolLeakCase, data: Any) -> list[str]:
    text = json.dumps(data, ensure_ascii=False)
    return contains_any(text, case.target_ids + case.forbidden_strings)


async def run_cases(tools, cases: list[ToolLeakCase]) -> list[ToolLeakResult]:
    from fabops.agent.gateway import McpGateway
    from fabops.authz.token import issue_token
    from fabops.mcp_server.server import build_server, demo_scope_resolver

    secret = secrets.token_urlsafe(48)  # ephemeral: the server lives only in this process
    app = build_server(tools, demo_scope_resolver(), secret).http_app()
    out = []
    for c in cases:
        async with McpGateway.in_process(app, issue_token(c.asker_user_id, secret)) as gw:
            r = await gw.call(c.tool, dict(c.args))
        matched = judge(c, r.data) if r.ok else []
        found = r.data.get("found") if r.ok and isinstance(r.data, dict) else None
        out.append(
            ToolLeakResult(
                c.cid, c.boundary, c.tool, c.asker_user_id, bool(matched), matched, found, r.error
            )
        )
    return out


def summarize(results: list[ToolLeakResult]) -> dict[str, Any]:
    by: dict[str, dict[str, int]] = defaultdict(lambda: {"leaked": 0, "n": 0, "errors": 0})
    for r in results:
        for key in (f"tool:{r.tool}", f"boundary:{r.boundary}", "all"):
            by[key]["n"] += 1
            by[key]["leaked"] += r.leaked
            by[key]["errors"] += r.error is not None
    return dict(sorted(by.items()))


def run(system: str, cases_path: Path = TOOL_CASES) -> dict[str, Any]:
    cases = load_tool_leak_cases(cases_path)
    if system == "tools-jsonl":
        cases = [c for c in cases if c.tool in MES_TOOLS]
    results = asyncio.run(run_cases(build_tools(system), cases))
    run_id = f"{datetime.now(UTC):%Y%m%dT%H%M%SZ}-leak-{system}"
    RESULTS.mkdir(parents=True, exist_ok=True)
    with (RESULTS / f"{run_id}.jsonl").open("w", encoding="utf-8", newline="\n") as f:
        for r in results:
            f.write(json.dumps(asdict(r), ensure_ascii=False) + "\n")
    summary = {
        "run_id": run_id,
        "system": system,
        "cases_sha256": files_sha256([cases_path]),
        "git": git_state(),
        "by": summarize(results),
    }
    (RESULTS / f"{run_id}.summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return summary


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--system", required=True, choices=SYSTEMS)
    p.add_argument("--cases", type=Path, default=TOOL_CASES)
    p.add_argument("--fail-on-leak", action="store_true", help="exit 1 if any case leaks")
    args = p.parse_args(argv)
    summary = run(args.system, args.cases)
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    print(json.dumps({k: summary[k] for k in ("run_id", "by")}, indent=2, ensure_ascii=False))
    total = summary["by"]["all"]
    if args.fail_on_leak and (total["leaked"] or total["errors"]):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
