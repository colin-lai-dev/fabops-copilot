"""Three-way comparison on the agent scenarios (PLAN Phase 2): RAG only vs fixed workflow vs agent.

Systems (same LLM, same retriever, same MCP tools and permission checks):
- `rag`: the Phase 1 default RAG (`rag-hybrid-bm25`), one retrieval, no tools, never proposes.
- `fixed`: the fixed workflow graph (lot → equipment → SOP → incidents, then one LLM call).
- `agent`: the LangGraph agent (the LLM picks each step, at most 8 tool calls).

Metrics per scenario (`score_scenario`), each reported with n:
- success: every fact group met, no forbidden string, refusal as expected (when set), and the
  proposal matches the expected one (or no proposal when none is expected);
- tool selection: the expected tools were all called successfully (agent/fixed only);
- ungrounded ids: lot / equipment / chamber / alarm / document ids in the answer, citations or
  proposal that appear neither in the question nor in what the system saw (捏造 ID);
- steps (tool calls), LLM calls, tokens, cost, latency.

Runs stay waiting at approval (the proposal is what is scored); nothing is executed.

    uv run python -m evals.agent_eval --split dev --system agent
    uv run python -m evals.agent_eval --split test --system agent --allow-test   # gate only
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import secrets
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from evals.corpus import load_corpus
from evals.run import RESULTS, files_sha256, git_state, load_scopes
from evals.schema import AgentScenario, load_agent_scenarios
from evals.score import contains_fact, text_says_refusal
from evals.synonyms import synonym_table

ROOT = Path(__file__).resolve().parents[1]
SCENARIOS = ROOT / "evals" / "agent"
SYSTEMS = ("rag", "fixed", "agent")
ID_RE = re.compile(
    r"\bFX\dL\d{5}\b"  # lot
    r"|\bFX\d-[A-Z]+-\d{2}(?:-CH[A-D])?\b"  # equipment / chamber
    r"|\b[A-Z]{3}-[A-Z0-9]{3}-\d{4}\b"  # alarm code
    r"|\bSOP-FX\d-[A-Z0-9-]+-v\d+\b|\bGEN-[A-Z0-9-]+\b|\bINC-\d{4}-\d{4}\b"  # documents
)


@dataclass
class ScenarioResult:
    sid: str
    category: str
    system: str
    success: bool
    facts_ok: bool
    forbidden_hit: list[str]
    refusal_ok: bool | None
    proposal_ok: bool
    tools_ok: bool | None
    ungrounded_ids: list[str]
    steps: int
    llm_calls: int
    input_tokens: int
    output_tokens: int
    cost_usd: float
    latency_ms: float
    status: str
    answer: str
    citations: list[str]
    proposal: dict[str, Any] | None
    tools_called: list[str] = field(default_factory=list)
    error: str | None = None


@dataclass
class Observed:
    """What one system produced and saw for one scenario."""

    answer: str
    citations: list[str]
    refused: bool
    proposal: dict[str, Any] | None
    calls: list[dict[str, Any]]
    seen: str  # tool results / retrieved documents, for the grounding check
    steps: int
    usage: dict[str, float]
    status: str
    error: str | None = None


def score_scenario(s: AgentScenario, o: Observed, system: str, latency_ms: float) -> ScenarioResult:
    syn = synonym_table()
    facts_ok = all(
        any(contains_fact(o.answer, alt, syn) for alt in group) for group in s.expected_facts
    )
    forbidden = [
        f
        for f in s.forbidden_strings
        if f in o.answer or f in json.dumps(o.proposal or {}, ensure_ascii=False)
    ]
    refused = o.refused or text_says_refusal(o.answer)
    refusal_ok = None if s.expect_refusal is None else refused == s.expect_refusal
    if s.expected_proposal is None:
        proposal_ok = o.proposal is None
    else:
        proposal_ok = o.proposal is not None and (
            o.proposal.get("action"),
            o.proposal.get("target_id"),
        ) == (s.expected_proposal.action, s.expected_proposal.target_id)
    called = [c["tool"] for c in o.calls if c.get("ok")]
    tools_ok = None if system == "rag" else set(s.expected_tools) <= set(called)
    produced = " ".join([o.answer, *o.citations, (o.proposal or {}).get("target_id", "")])
    grounded = set(ID_RE.findall(s.question)) | set(ID_RE.findall(o.seen))
    ungrounded = sorted(set(ID_RE.findall(produced)) - grounded)
    success = (
        o.error is None and facts_ok and not forbidden and refusal_ok is not False and proposal_ok
    )
    u = o.usage
    return ScenarioResult(
        s.sid, s.category, system, success, facts_ok, forbidden, refusal_ok, proposal_ok,
        tools_ok, ungrounded, o.steps, int(u.get("llm_calls", 0)), int(u.get("input_tokens", 0)),
        int(u.get("output_tokens", 0)), float(u.get("cost_usd", 0.0)), latency_ms, o.status,
        o.answer, o.citations, o.proposal, called, o.error,
    )  # fmt: skip


def _rate(values: list[bool | None]) -> dict[str, Any]:
    vals = [v for v in values if v is not None]
    return {
        "rate": round(sum(vals) / len(vals), 3) if vals else None,
        "k": sum(vals),
        "n": len(vals),
    }


def summarize(results: list[ScenarioResult]) -> dict[str, Any]:
    def block(rs: list[ScenarioResult]) -> dict[str, Any]:
        n = len(rs)
        return {
            "n": n,
            "success": _rate([r.success for r in rs]),
            "tool_selection": _rate([r.tools_ok for r in rs]),
            "ungrounded_id_rate": _rate([bool(r.ungrounded_ids) for r in rs]),
            "proposal_ok": _rate([r.proposal_ok for r in rs]),
            "mean_steps": round(sum(r.steps for r in rs) / n, 2) if n else None,
            "mean_llm_calls": round(sum(r.llm_calls for r in rs) / n, 2) if n else None,
            "mean_tokens": round(sum(r.input_tokens + r.output_tokens for r in rs) / n)
            if n
            else None,
            "mean_cost_usd": round(sum(r.cost_usd for r in rs) / n, 6) if n else None,
            "mean_latency_s": round(sum(r.latency_ms for r in rs) / n / 1000, 1) if n else None,
            "errors": sum(r.error is not None for r in rs),
        }

    cats = sorted({r.category for r in results})
    return {
        "all": block(results),
        **{c: block([r for r in results if r.category == c]) for c in cats},
    }


# ---------------------------------------------------------------- systems


class Runner:
    """Wires the real components once per eval run (Postgres, retriever, LLM, MCP in-process)."""

    def __init__(self) -> None:
        import psycopg
        from langgraph.checkpoint.memory import InMemorySaver

        from evals.systems import make_retriever
        from fabops.agent.proposals import InMemoryProposalStore
        from fabops.agent.service import AgentService
        from fabops.authz.trace import Tracer
        from fabops.config import get_settings
        from fabops.llm.client import LLMClient
        from fabops.mcp_server.server import build_server, demo_scope_resolver
        from fabops.mcp_server.store import PgMesStore
        from fabops.mcp_server.tools import MesTools

        url = get_settings().database_url
        self.retriever = make_retriever()
        self.tracer = Tracer.from_env()
        self.llm = LLMClient.from_env()
        tools = MesTools(PgMesStore(lambda: psycopg.connect(url)), self.retriever, self.tracer)
        self.secret = secrets.token_urlsafe(48)
        self.app = build_server(tools, demo_scope_resolver(), self.secret).http_app()
        self.service = AgentService(self.llm, InMemoryProposalStore(), InMemorySaver(), self.tracer)
        self.scopes = load_scopes()
        self.docs = load_corpus()
        self._rag = None

    async def graph(self, s: AgentScenario, mode: str) -> Observed:
        from fabops.agent.gateway import McpGateway
        from fabops.authz.token import issue_token

        async with McpGateway.in_process(self.app, issue_token(s.user_id, self.secret)) as gw:
            r = await self.service.ask(
                s.question, user_id=s.user_id, scope=self.scopes[s.user_id], gateway=gw, mode=mode
            )
        return Observed(
            r.answer, r.citations, r.refused, r.proposal, r.calls, "\n".join(r.tool_results),
            r.steps, r.usage, r.status,
        )  # fmt: skip

    def rag(self, s: AgentScenario) -> Observed:
        from evals.systems import load_system

        if self._rag is None:
            self._rag = load_system("rag-hybrid-bm25")
        out = self._rag.answer(s.question, self.scopes[s.user_id])
        seen = "\n".join(self.docs[d]["body_md"] for d in out.retrieved if d in self.docs)
        usage = {
            "input_tokens": out.input_tokens, "output_tokens": out.output_tokens,
            "cost_usd": out.cost_usd, "llm_calls": 1 if out.input_tokens else 0,
        }  # fmt: skip
        return Observed(
            out.answer, out.citations, out.refused, None, [], seen + "\n" + " ".join(out.retrieved),
            0, usage, "done", out.error,
        )  # fmt: skip


async def run_all(system: str, scenarios: list[AgentScenario]) -> list[ScenarioResult]:
    runner = Runner()
    out = []
    for s in scenarios:
        t0 = time.perf_counter()
        try:
            o = runner.rag(s) if system == "rag" else await runner.graph(s, system)
        except Exception as e:  # keep going; the error is part of the result
            o = Observed("", [], False, None, [], "", 0, {}, "error", f"{type(e).__name__}: {e}")
        out.append(score_scenario(s, o, system, (time.perf_counter() - t0) * 1000))
        print(f"{s.sid} {system}: success={out[-1].success} steps={o.steps}", file=sys.stderr)
    return out


def run(split: str, system: str, allow_test: bool = False) -> dict[str, Any]:
    if split == "test" and not allow_test:
        raise SystemExit("test split: only at a gate, with Colin's approval (--allow-test)")
    paths = sorted((SCENARIOS / split).glob("*.jsonl"))
    scenarios = load_agent_scenarios(paths)
    from fabops.config import get_settings

    cfg = get_settings()
    results = asyncio.run(run_all(system, scenarios))
    run_id = f"{datetime.now(UTC):%Y%m%dT%H%M%SZ}-agent-{split}-{system}"
    RESULTS.mkdir(parents=True, exist_ok=True)
    with (RESULTS / f"{run_id}.jsonl").open("w", encoding="utf-8", newline="\n") as f:
        for r in results:
            f.write(json.dumps(asdict(r), ensure_ascii=False) + "\n")
    summary = {
        "run_id": run_id,
        "split": split,
        "system": system,
        "model": f"{cfg.llm_provider}/{cfg.llm_model}",
        "scenarios_sha256": files_sha256(paths),
        "git": git_state(),
        "metrics": summarize(results),
    }
    (RESULTS / f"{run_id}.summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return summary


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--split", choices=("dev", "test"), default="dev")
    p.add_argument("--system", choices=SYSTEMS, required=True)
    p.add_argument("--allow-test", action="store_true")
    args = p.parse_args(argv)
    summary = run(args.split, args.system, args.allow_test)
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    print(
        json.dumps(
            {k: summary[k] for k in ("run_id", "model", "metrics")}, indent=2, ensure_ascii=False
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
