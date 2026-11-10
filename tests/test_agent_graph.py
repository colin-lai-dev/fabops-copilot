"""Agent graph (ADR-0006): steps, limits, retries, approval, idempotency, identity, fixed workflow.

The LLM is a scripted fake (no API calls); tools go through the real FastMCP server in-process,
with the JSONL MES store, so every tool call crosses the JWT boundary (ADR-0001).
"""

from __future__ import annotations

import asyncio
import json

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from fabops.agent.gateway import McpGateway, ToolResult
from fabops.agent.graph import FALLBACK_ANSWER, OLD_RESULT_CHARS, fixed_next_call
from fabops.agent.proposals import InMemoryProposalStore
from fabops.agent.service import AgentService
from fabops.authz.policy import scope_of_user
from fabops.authz.token import issue_token
from fabops.authz.trace import Tracer
from fabops.data.world import DEMO_USERS
from fabops.llm.client import Completion, LLMClient
from fabops.mcp_server.server import build_server, demo_scope_resolver
from fabops.mcp_server.store import JsonlMesStore
from fabops.mcp_server.tools import MesTools
from fabops.rag.retrieve import Hit, Retrieval

SECRET = "agent-test-secret-" + "y" * 32
SCOPES = {
    u: scope_of_user({"fabs": f, "departments": d, "clearance": c}) for u, _, f, d, c in DEMO_USERS
}
STORE = JsonlMesStore()
EQ = "FX1-ETCHER-02"
SOP = "SOP-FX1-ETC-PRS-0412-v2"


class FakeSearcher:
    def search(self, query, scope, doc_type=None):
        hits = [
            Hit("c1", SOP, "## 4. 處置步驟\n2. 暫停該腔體派貨。", "FX1", "etch", 1, 1.0, {}, "sop"),
            Hit("c2", "INC-2026-0007", "腔體壓力異常…", "FX1", "etch", 1, 0.9, {}, "incident"),
        ]
        return Retrieval([h for h in hits if h.doc_type == doc_type], {})


class Scripted:
    """Fake provider: returns the queued replies in order and records every prompt."""

    name = "fake"

    def __init__(self, replies):
        self.replies, self.prompts = list(replies), []

    def complete(self, messages, model, temperature, max_tokens):
        self.prompts.append(messages)
        reply = self.replies.pop(0) if self.replies else "not json"
        text = reply if isinstance(reply, str) else json.dumps(reply, ensure_ascii=False)
        return Completion(text, 100, 20)


def call(tool, **args):
    return {"action": "call_tool", "tool": tool, "args": args}


def finish(answer, citations=(), refused=False):
    return {"action": "finish", "answer": answer, "citations": list(citations), "refused": refused}


@pytest.fixture
def env(tmp_path):
    tracer = Tracer(tmp_path / "traces.jsonl")
    app = build_server(
        MesTools(STORE, FakeSearcher(), tracer), demo_scope_resolver(), SECRET
    ).http_app()

    def make(replies, *, user="eng_fx1_etch", mode="agent", question=None, max_steps=8):
        provider = Scripted(replies)
        llm = LLMClient(provider, "fake-1", tmp_path / "cache", tmp_path / "usage.jsonl")
        proposals = InMemoryProposalStore()
        svc = AgentService(llm, proposals, InMemorySaver(), tracer, max_steps=max_steps)

        async def ask(q=question or f"{EQ} 腔體壓力異常，現在該怎麼處理？"):
            async with McpGateway.in_process(app, issue_token(user, SECRET)) as gw:
                return await svc.ask(q, user_id=user, scope=SCOPES[user], gateway=gw, mode=mode)

        return svc, provider, proposals, ask

    return make


def run(coro):
    return asyncio.run(coro)


def test_multi_step_answer_and_citation_exit_check(env):
    _, provider, _, ask = env(
        [
            call("get_equipment_status", equipment_id=EQ),
            call("search_sop", query="腔體壓力異常"),
            finish("依 SOP 先暫停腔體派貨。", [SOP, "SOP-INVENTED-999"]),
        ]
    )
    r = run(ask())
    assert r.status == "done" and r.steps == 2
    assert [c["tool"] for c in r.calls] == ["get_equipment_status", "search_sop"]
    assert r.citations == [SOP]  # invented doc id dropped at the output exit
    assert r.usage["llm_calls"] == 3


def test_step_limit_stops_at_eight_and_marks_incomplete(env):
    loop = [call("get_dispatch_log", equipment_id=EQ, limit=n) for n in range(1, 20)]
    _, _, _, ask = env(loop[:8] + [{"answer": "只查到部分派貨紀錄。", "citations": []}])
    r = run(ask())
    assert r.steps == 8 and r.status == "incomplete"
    assert r.answer == "只查到部分派貨紀錄。"


def test_invalid_llm_output_falls_back(env):
    _, provider, _, ask = env(["garbage"] * 10)
    r = run(ask())
    assert r.status == "incomplete" and r.answer == FALLBACK_ANSWER and r.refused
    assert len(provider.prompts) == 4  # 2 decisions x (try + repair retry); no tools to summarize


def test_unknown_and_duplicate_tool_calls_become_errors(env):
    _, _, _, ask = env(
        [
            call("delete_everything"),
            call("get_equipment_status", equipment_id=EQ),
            call("get_equipment_status", equipment_id=EQ),
            finish("完成"),
        ]
    )
    r = run(ask())
    assert [c["ok"] for c in r.calls] == [False, True, False]
    assert "沒有這個工具" in r.calls[0]["error"] and "重複" in r.calls[2]["error"]


def _propose(target, action="inhibit_chamber"):
    return {
        "action": "propose",
        "proposal": {"action": action, "target_id": target, "reason": "壓力超限，依 SOP 第 2 步"},
        "answer": "建議暫停腔體派貨。",
        "citations": [SOP],
    }


def test_proposal_waits_for_approval_then_executes_once(env):
    chamber = f"{EQ}-CHA"
    svc, _, proposals, ask = env(
        [call("get_equipment_status", equipment_id=EQ), call("search_sop", query="壓力"),
         _propose(chamber)]
    )  # fmt: skip
    r = run(ask())
    assert r.status == "awaiting_approval" and r.proposal["status"] == "pending"
    pid = r.proposal["proposal_id"]

    done = run(svc.decide(r.thread_id, approved=True, approver="lead_fx1_multi"))
    assert done.status == "executed" and "已核准並執行（模擬）" in done.answer
    assert done.citations == [SOP]
    assert [a.event for a in proposals.audit(pid)] == ["proposed", "approved", "executed"]
    assert proposals.audit(pid)[1].actor == "lead_fx1_multi"

    with pytest.raises(ValueError):  # the run is finished; a second decision is refused
        run(svc.decide(r.thread_id, approved=True, approver="lead_fx1_multi"))
    again, executed_now = proposals.execute_once(pid)
    assert again.status == "executed" and executed_now is False


def test_rejected_proposal_is_not_executed(env):
    svc, _, proposals, ask = env(
        [call("get_equipment_status", equipment_id=EQ), _propose(f"{EQ}-CHA")]
    )
    r = run(ask())
    done = run(svc.decide(r.thread_id, approved=False, approver="lead_fx1_multi", note="先重測"))
    assert done.status == "rejected" and "未獲核准" in done.answer
    assert [a.event for a in proposals.audit()] == ["proposed", "rejected"]


def test_proposal_for_an_unseen_id_is_refused(env):
    _, _, proposals, ask = env(
        [_propose("FX1L09999", "hold_lot"), finish("無法提出建議", refused=True)]
    )
    r = run(ask())
    assert r.status == "done" and r.proposal is None and proposals.audit() == []
    assert "沒有出現在任何工具結果中" in r.calls[0]["error"]


def test_identity_never_reaches_the_prompt(env, tmp_path):
    _, provider, _, ask = env(
        [call("get_equipment_status", equipment_id=EQ), finish("ok")], user="lead_fx1_multi"
    )
    run(ask())
    text = json.dumps(provider.prompts, ensure_ascii=False)
    for secret in ("lead_fx1_multi", SCOPES["lead_fx1_multi"].key(), "clearance", SECRET):
        assert secret not in text
    trace = (tmp_path / "traces.jsonl").read_text("utf-8")
    assert "lead_fx1_multi" not in trace and "dropped_fields" not in trace


def test_permissions_hold_inside_the_agent(env):
    """The agent of a FX2 user cannot read FX1 equipment, whatever the LLM asks for."""
    _, _, _, ask = env(
        [call("get_equipment_status", equipment_id=EQ), finish("查不到")], user="eng_fx2_litho"
    )
    r = run(ask())
    assert json.loads(r.tool_results[0])["found"] is False


def test_old_results_are_trimmed_in_the_prompt(env):
    eqs = ["FX1-ETCHER-01", "FX1-ETCHER-02", "FX1-ETCHER-03", "FX1-CVD-01", "FX1-CVD-02"]
    _, provider, _, ask = env(
        [call("get_equipment_status", equipment_id=e) for e in eqs] + [finish("ok")],
        user="lead_fx1_multi",
    )
    run(ask())
    last = provider.prompts[-1][-1]["content"]
    assert last.count("已截斷") >= 2  # the oldest results; the last KEEP_FULL stay in full
    first_block = last.split("</工具結果>")[0]
    assert len(first_block) < OLD_RESULT_CHARS + 300


def test_transient_tool_error_is_retried_once():
    from fabops.agent.graph import AgentDeps, build_graph

    class Flaky:
        def __init__(self):
            self.n = 0

        async def list_tools(self):
            return []

        async def call(self, name, args):
            self.n += 1
            if self.n == 1:
                return ToolResult(False, error="ConnectError", transient=True)
            return ToolResult(True, {"found": True})

    gw = Flaky()
    deps = AgentDeps(None, None, "u", gw, InMemoryProposalStore(), Tracer("/dev/null"))
    tools = build_graph(deps).get_graph()  # compiles
    assert tools is not None
    from fabops.agent.graph import make_nodes

    node = make_nodes(deps)["tools"]
    out = run(node({"pending": {"tool": "get_lot_history", "args": {"lot_id": "FX1L00001"}}}))
    assert out["calls"][0]["ok"] and gw.n == 2


# ---------------------------------------------------------------- fixed workflow


def test_fixed_workflow_order_and_shared_nodes(env):
    lot = next(
        a["lot_id"]
        for a in STORE.views["alarms"]
        if a["lot_id"] and a["fab"] == "FX1" and a["department"] == "etch"
    )
    _, provider, _, ask = env(
        [finish("固定流程回答", [SOP])], mode="fixed", question=f"批號 {lot} 有 alarm，該怎麼處理？"
    )
    r = run(ask())
    assert [c["tool"] for c in r.calls] == [
        "get_lot_history",
        "get_equipment_status",
        "search_sop",
        "search_similar_incidents",
    ]
    assert r.status == "done" and r.citations == [SOP]
    assert len(provider.prompts) == 1  # only the final decision uses the LLM


def test_fixed_next_call_without_ids_searches_documents():
    s = {"question": "腔體壓力異常怎麼處理？", "calls": []}
    assert fixed_next_call(s) == {"tool": "search_sop", "args": {"query": "腔體壓力異常怎麼處理？"}}
