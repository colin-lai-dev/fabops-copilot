"""The triage agent as a custom LangGraph StateGraph (ADR-0006, option B).

Nodes (shared by both graphs):

    planner ─tool─▶ tools ─▶ trim_context ─▶ planner
       │ propose ─▶ propose ─▶ approval (interrupt) ─▶ execute ─▶ summarize ─▶ END
       └ finish / step limit / LLM failure ─────────────────────▶ summarize ─▶ END

- `agent` graph: the planner is the LLM (`agent` node), deciding the next step as JSON.
- `fixed` graph: the planner is a script (lot → equipment → SOP → similar incidents), then one
  LLM call decides propose / finish. The two differ only in who picks the next step.

Limits and recovery: at most `max_steps` tool calls (default 8), then `summarize` marks the run
incomplete; an invalid LLM reply is retried once by `LLMClient.structured` and once more here,
then the run falls back to `summarize`; a transport error on a tool call is retried once.

Identity: the user's scope and id live in `AgentDeps` (server side), never in the state, the
prompt or tool arguments (ADR-0001). The MCP gateway holds the token.
"""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt
from pydantic import BaseModel, Field

from fabops.agent.gateway import ToolGateway
from fabops.agent.prompts import (
    FALLBACK_ANSWER,
    FIXED_FINAL_NOTE,
    LIMIT_NOTE,
    RETRY_NOTE,
    SYSTEM_PROMPT,
)
from fabops.agent.proposals import (
    ACTIONS,
    ApprovalDenied,
    ProposalStore,
    approval_problem,
    as_dict,
)
from fabops.authz.scope import Scope
from fabops.authz.trace import Tracer
from fabops.llm.client import LLMClient, LLMResult
from fabops.mcp_server.store import MesStore
from fabops.mcp_server.tools import ID_PATTERN, TOOL_NAMES

MAX_STEPS = 8
KEEP_FULL = 3  # most recent tool results kept in full
MAX_RESULT_CHARS = 6000  # cap for a result kept in full (a typical MES result is ~3,000)
OLD_RESULT_CHARS = 1500  # cap for an older result after compaction
COMPACT_STR = 60  # older results: long strings (excerpts, alarm messages) are cut to this
COMPACT_LIST = 5  # older results: lists keep their first items (tools return newest first)
MAX_LLM_FAILURES = 2
# what a proposal's target id must look like, per ACTIONS[action][0]
TARGET_PATTERNS = {
    "lot_id": re.compile(r"^FX\dL\d{5}$"),
    "chamber_id": re.compile(r"^FX\d-[A-Z]+-\d{2}-CH[A-D]$"),
}

# ---------------------------------------------------------------- state and LLM schemas


class AgentState(TypedDict, total=False):
    thread_id: str  # run id (also the checkpoint thread); not an identity
    question: str
    mode: Literal["agent", "fixed"]
    steps: int  # tool calls executed
    calls: list[dict[str, Any]]  # {"step", "tool", "args", "ok", "result" | "error", "trimmed"}
    pending: dict[str, Any] | None  # the planner's decision, consumed by the next node
    proposal: dict[str, Any] | None
    answer: str
    citations: list[str]
    refused: bool
    status: str  # running | done | incomplete | awaiting_approval | executed | rejected | error
    llm_failures: int
    usage: dict[str, float]


class ProposalDraft(BaseModel):
    action: Literal["hold_lot", "inhibit_chamber", "request_pm"]
    target_id: str = Field(description="批號或腔體編號，必須出現在工具結果中")
    reason: str = Field(description="依據哪些查詢結果與 SOP 步驟")


class Decision(BaseModel):
    action: Literal["call_tool", "propose", "finish"]
    tool: str | None = Field(default=None, description="call_tool 時的工具名稱")
    args: dict[str, Any] = Field(default_factory=dict, description="call_tool 時的工具參數")
    proposal: ProposalDraft | None = Field(default=None, description="propose 時的寫入建議")
    answer: str = Field(default="", description="finish／propose 時給工程師的回答")
    citations: list[str] = Field(default_factory=list, description="依據的文件 doc_id")
    refused: bool = Field(default=False, description="不給建議或無法回答時為 true")


class FinalAnswer(BaseModel):
    answer: str
    citations: list[str] = Field(default_factory=list)
    refused: bool = False


@dataclass
class AgentDeps:
    """Server-side context of one run. Never serialized into the checkpoint."""

    llm: LLMClient | None
    scope: Scope | None
    user_id: str
    gateway: ToolGateway | None
    proposals: ProposalStore
    tracer: Tracer
    tools_spec: list[dict[str, Any]] = field(default_factory=list)
    max_steps: int = MAX_STEPS
    mes: MesStore | None = None  # approval: is the target visible to the approver?


# ---------------------------------------------------------------- helpers


def _usage(state: AgentState, results: list[LLMResult]) -> dict[str, float]:
    u = dict(state.get("usage") or {})
    for r in results:
        for k, v in (
            ("input_tokens", r.input_tokens),
            ("output_tokens", r.output_tokens),
            ("cost_usd", r.cost_usd or 0.0),
            ("latency_ms", r.latency_ms),
            ("llm_calls", 1),
        ):
            u[k] = u.get(k, 0) + v
    return u


def format_tools(spec: list[dict[str, Any]]) -> str:
    lines = []
    for t in spec:
        props = t.get("parameters", {}).get("properties", {})
        args = ", ".join(
            f"{k}{'' if k in t.get('parameters', {}).get('required', []) else '?'}" for k in props
        )
        lines.append(f"- {t['name']}({args})：{t['description']}")
    return "\n".join(lines)


def format_calls(calls: list[dict[str, Any]]) -> str:
    if not calls:
        return "（尚未呼叫任何工具）"
    out = []
    for c in calls:
        body = c["result"] if c["ok"] else f"錯誤：{c['error']}"
        args = json.dumps(c["args"], ensure_ascii=False)
        out.append(
            f'<工具結果 step="{c["step"]}" tool="{c["tool"]}" args=\'{args}\'>\n{body}\n</工具結果>'
        )
    return "\n\n".join(out)


def compact(text: str) -> str:
    """Shorten long strings and lists inside a JSON tool result, keeping its structure."""
    try:
        data = json.loads(text)
    except ValueError:
        return text[:OLD_RESULT_CHARS]

    def walk(x: Any) -> Any:
        if isinstance(x, dict):
            return {k: walk(v) for k, v in x.items()}
        if isinstance(x, list):
            head = [walk(v) for v in x[:COMPACT_LIST]]
            return head + ([f"…另 {len(x) - COMPACT_LIST} 筆"] if len(x) > COMPACT_LIST else [])
        if isinstance(x, str) and len(x) > COMPACT_STR:
            return x[:COMPACT_STR] + "…"
        return x

    return json.dumps(walk(data), ensure_ascii=False)


def seen_text(calls: list[dict[str, Any]]) -> str:
    """Everything the tools returned in this run (before trimming is applied to the prompt)."""
    return "\n".join(c.get("full", c.get("result", "")) for c in calls if c["ok"])


def seen_doc_ids(calls: list[dict[str, Any]]) -> set[str]:
    ids: set[str] = set()
    for c in calls:
        if c["ok"] and c["tool"] in ("search_sop", "search_similar_incidents"):
            ids.update(re.findall(r'"doc_id": "([^"]+)"', c.get("full", c["result"])))
    return ids


# ---------------------------------------------------------------- nodes


def make_nodes(deps: AgentDeps) -> dict[str, Callable]:
    def trace(event: str, state: AgentState | None = None, **fields: Any) -> None:
        if state is not None:
            fields["thread_id"] = state.get("thread_id")  # groups a run into one trace
        deps.tracer.event(event, scope=deps.scope.key() if deps.scope else None, **fields)

    async def decide(state: AgentState, note: str = "") -> dict[str, Any]:
        """One LLM decision; failures are counted and fall back to summarize."""
        tools = format_tools(deps.tools_spec)
        if state.get("llm_failures", 0):
            # A different prompt, so the retry is not served the cached invalid reply.
            note = RETRY_NOTE + note
        messages = [
            {
                "role": "system",
                "content": SYSTEM_PROMPT.format(max_steps=deps.max_steps, tools=tools),
            },
            {
                "role": "user",
                "content": f"問題：{state['question']}\n\n已執行的工具（{state.get('steps', 0)}/"
                f"{deps.max_steps}）：\n{format_calls(state.get('calls', []))}\n\n"
                f"{note}請決定下一步。",
            },
        ]
        assert deps.llm is not None and deps.scope is not None
        try:
            d, results = await asyncio.to_thread(
                deps.llm.structured, messages, Decision, deps.scope, max_tokens=1024,
                purpose="agent",
            )  # fmt: skip
        except ValueError as e:
            failures = state.get("llm_failures", 0) + 1
            trace(
                "agent_step",
                state,
                step=state.get("steps", 0),
                decision="invalid",
                error_type=type(e).__name__,
            )
            kind = "limit" if failures >= MAX_LLM_FAILURES else "retry"
            return {"llm_failures": failures, "pending": {"kind": kind}}
        trace("agent_step", state, step=state.get("steps", 0), decision=d.action, tool=d.tool)
        return {"pending": {"kind": d.action, **d.model_dump()}, "usage": _usage(state, results)}

    async def agent(state: AgentState) -> dict[str, Any]:
        if state.get("steps", 0) >= deps.max_steps:
            return {"pending": {"kind": "limit"}}
        return await decide(state)

    async def fixed(state: AgentState) -> dict[str, Any]:
        nxt = fixed_next_call(state)
        if nxt is not None and state.get("steps", 0) < deps.max_steps:
            return {"pending": {"kind": "call_tool", **nxt}}
        out = await decide(state, note=FIXED_FINAL_NOTE + "\n")
        if out["pending"]["kind"] == "call_tool":
            out["pending"] = {"kind": "limit"}
        return out

    async def tools(state: AgentState) -> dict[str, Any]:
        p = state["pending"] or {}
        step = state.get("steps", 0) + 1
        name, args = p.get("tool") or "", dict(p.get("args") or {})
        call: dict[str, Any] = {"step": step, "tool": name, "args": args}
        previous = next(
            (c for c in state.get("calls", []) if c["tool"] == name and c["args"] == args), None
        )
        if name not in TOOL_NAMES:
            call.update(ok=False, error=f"沒有這個工具：{name}")
        elif previous is not None:
            call.update(ok=False, error=f"與 step {previous['step']} 重複，請改用已有的結果")
        elif deps.gateway is None:
            call.update(ok=False, error="工具目前無法使用")
        else:
            r = await deps.gateway.call(name, args)
            if not r.ok and r.transient:
                r = await deps.gateway.call(name, args)  # one retry on transport errors
            if r.ok:
                text = json.dumps(r.data, ensure_ascii=False)
                call.update(ok=True, result=text, full=text)
            else:
                call.update(ok=False, error=r.error)
        trace("tool_call", state, step=step, tool=name, status="ok" if call["ok"] else "error")
        return {"steps": step, "calls": [*state.get("calls", []), call], "pending": None}

    def trim_context(state: AgentState) -> dict[str, Any]:
        """Keep the last KEEP_FULL results whole; compact older ones without losing ids.

        Compaction keeps the JSON structure (every key, id and status) and only shortens long
        strings and long lists, so the agent can still read, e.g., a chamber's status from an
        older result. Hard cuts apply only beyond MAX_RESULT_CHARS / OLD_RESULT_CHARS.
        """
        calls = [dict(c) for c in state.get("calls", [])]
        ok_idx = [i for i, c in enumerate(calls) if c["ok"]]
        recent = set(ok_idx[-KEEP_FULL:])
        for i in ok_idx:
            full = calls[i]["full"]
            text, limit = (
                (full, MAX_RESULT_CHARS) if i in recent else (compact(full), OLD_RESULT_CHARS)
            )
            if len(text) > limit:
                text = text[:limit] + f"…（已截斷，原長 {len(full)} 字）"
            calls[i]["result"], calls[i]["trimmed"] = text, text != full
        return {"calls": calls}

    def propose(state: AgentState) -> dict[str, Any]:
        p = state["pending"] or {}
        draft = p.get("proposal") or {}
        action, target = draft.get("action", ""), str(draft.get("target_id", "")).strip()
        problem = None
        if action not in ACTIONS:
            problem = f"不支援的建議類型：{action}"
        elif not ID_PATTERN.match(target):
            problem = "建議的目標編號格式不正確"
        elif not TARGET_PATTERNS[ACTIONS[action][0]].match(target):
            problem = f"{action} 的 target_id 必須是{ACTIONS[action][0]}"
        elif target not in seen_text(state.get("calls", [])):
            problem = f"{target} 沒有出現在任何工具結果中，請先查詢確認"
        if problem is not None:
            step = state.get("steps", 0) + 1
            bad = {"step": step, "tool": "propose", "args": draft, "ok": False, "error": problem}
            trace("proposal", state, step=step, status="invalid")
            return {"steps": step, "calls": [*state.get("calls", []), bad], "pending": None}
        rec, _ = deps.proposals.create(
            state["thread_id"], deps.user_id, action, target, str(draft.get("reason", ""))[:500]
        )
        trace("proposal", state, proposal_id=rec.proposal_id, action=action, status=rec.status)
        return {
            "proposal": as_dict(rec),
            "answer": p.get("answer", ""),
            "citations": list(p.get("citations") or []),
            "refused": False,
            "status": "awaiting_approval",
        }

    def approval(state: AgentState) -> dict[str, Any]:
        prop = state["proposal"] or {}
        decision = interrupt(
            {k: prop.get(k) for k in ("proposal_id", "action", "target_id", "reason")}
        )
        approved = bool(decision.get("approved"))
        approver = str(decision.get("approver") or "").strip()
        if not approver:
            raise ValueError("an approval needs the approver's user id (set by the API)")
        # deps.user_id / deps.scope are the approver's here (AgentService.decide).
        problem = (
            approval_problem(prop, approver, deps.scope, deps.mes)
            if approver == deps.user_id
            else "approver does not match the authenticated user"
        )
        if problem is not None:
            deps.proposals.deny(prop["proposal_id"], approver, problem)
            trace("approval", state, proposal_id=prop["proposal_id"], status="denied")
            raise ApprovalDenied(problem)  # the run stays waiting at approval
        rec = deps.proposals.decide(
            prop["proposal_id"], approved, approver, str(decision.get("note", ""))
        )
        trace("approval", state, proposal_id=rec.proposal_id, status=rec.status)
        return {"proposal": as_dict(rec)}

    def execute(state: AgentState) -> dict[str, Any]:
        prop = state["proposal"] or {}
        if prop.get("status") == "approved":
            rec, now = deps.proposals.execute_once(prop["proposal_id"])
            trace("execute", state, proposal_id=rec.proposal_id, status=rec.status, cached=not now)
            prop = as_dict(rec)
        return {"proposal": prop}

    async def summarize(state: AgentState) -> dict[str, Any]:
        p = state.get("pending") or {}
        out: dict[str, Any] = {}
        if state.get("proposal"):
            prop = state["proposal"]
            label = ACTIONS[prop["action"]][1]
            outcome = {
                "executed": f"已核准並執行（模擬）：{label} {prop['target_id']}。",
                "rejected": f"建議未獲核准：{label} {prop['target_id']}。",
            }.get(prop["status"], f"建議狀態：{prop['status']}。")
            out = {
                "answer": f"{state.get('answer', '')}\n\n{outcome}".strip(),
                "status": prop["status"] if prop["status"] in ("executed", "rejected") else "done",
            }
            citations = state.get("citations", [])
        elif p.get("kind") == "finish":
            out = {
                "answer": p.get("answer", ""),
                "refused": bool(p.get("refused")),
                "status": "done",
            }
            citations = list(p.get("citations") or [])
        else:  # step limit or repeated LLM failure
            out, citations = await _limit_answer(state)
        # Output exit check: cite only documents a search tool returned in this run.
        allowed = seen_doc_ids(state.get("calls", []))
        out["citations"] = [c for c in dict.fromkeys(citations) if c in allowed]
        trace(
            "agent_done", state, steps=state.get("steps", 0), status=out.get("status"),
            cited=out["citations"], texts={"answer": out.get("answer", "")},
        )  # fmt: skip
        return {**out, "pending": None}

    async def _limit_answer(state: AgentState) -> tuple[dict[str, Any], list[str]]:
        if deps.llm is None or deps.scope is None or not state.get("calls"):
            return {"answer": FALLBACK_ANSWER, "refused": True, "status": "incomplete"}, []
        system = SYSTEM_PROMPT.format(max_steps=deps.max_steps, tools="（不可再呼叫工具）")
        user = f"問題：{state['question']}\n\n{format_calls(state['calls'])}\n\n{LIMIT_NOTE}"
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        try:
            f, results = await asyncio.to_thread(
                deps.llm.structured, messages, FinalAnswer, deps.scope, max_tokens=1024,
                purpose="agent-limit",
            )  # fmt: skip
        except ValueError:
            return {"answer": FALLBACK_ANSWER, "refused": True, "status": "incomplete"}, []
        return (
            {
                "answer": f.answer,
                "refused": f.refused,
                "status": "incomplete",
                "usage": _usage(state, results),
            },
            f.citations,
        )

    return {
        "agent": agent,
        "fixed": fixed,
        "tools": tools,
        "trim_context": trim_context,
        "propose": propose,
        "approval": approval,
        "execute": execute,
        "summarize": summarize,
    }


# ---------------------------------------------------------------- fixed workflow script

LOT_RE = re.compile(r"\bFX\dL\d{5}\b")
EQUIPMENT_RE = re.compile(r"\bFX\d-[A-Z]+-\d{2}\b")
ALARM_RE = re.compile(r"\b[A-Z]{3}-[A-Z0-9]{3}-\d{4}\b")


def _result(state: AgentState, tool: str) -> dict[str, Any] | None:
    for c in state.get("calls", []):
        if c["tool"] == tool and c["ok"]:
            try:
                return json.loads(c["full"])
            except ValueError:
                return None
    return None


def fixed_next_call(state: AgentState) -> dict[str, Any] | None:
    """lot → equipment → SOP → similar incidents (ADR-0006), each at most once."""
    q, called = state["question"], {c["tool"] for c in state.get("calls", [])}
    lots = LOT_RE.findall(q)
    if lots and "get_lot_history" not in called:
        return {"tool": "get_lot_history", "args": {"lot_id": lots[0]}}
    lot = _result(state, "get_lot_history") or {}
    rows = (lot.get("alarms") or []) + (lot.get("dispatches") or [])
    # EQUIPMENT_RE also matches the equipment part of a chamber id (FX1-ETCHER-01-CHA).
    eq = (EQUIPMENT_RE.findall(q) or [None])[0] or (rows[0]["equipment_id"] if rows else None)
    if eq and "get_equipment_status" not in called:
        return {"tool": "get_equipment_status", "args": {"equipment_id": eq}}
    status = _result(state, "get_equipment_status") or {}
    alarms = (lot.get("alarms") or []) + (status.get("recent_alarms") or [])
    code = (ALARM_RE.findall(q) or [alarms[0]["alarm_code"] if alarms else ""])[0]
    query = f"{code} {q}".strip()
    if "search_sop" not in called:
        return {"tool": "search_sop", "args": {"query": query}}
    if "search_similar_incidents" not in called:
        return {"tool": "search_similar_incidents", "args": {"query": query}}
    return None


# ---------------------------------------------------------------- graphs


def _after_planner(state: AgentState) -> str:
    kind = (state.get("pending") or {}).get("kind")
    return {"call_tool": "tools", "propose": "propose", "retry": "planner"}.get(kind, "summarize")


def _after_propose(state: AgentState) -> str:
    return "approval" if state.get("status") == "awaiting_approval" else "planner"


def build_graph(deps: AgentDeps, mode: Literal["agent", "fixed"] = "agent", checkpointer=None):
    nodes = make_nodes(deps)
    g = StateGraph(AgentState)
    g.add_node("planner", nodes[mode])
    for name in ("tools", "trim_context", "propose", "approval", "execute", "summarize"):
        g.add_node(name, nodes[name])
    g.add_edge(START, "planner")
    g.add_conditional_edges("planner", _after_planner, ["tools", "propose", "planner", "summarize"])
    g.add_edge("tools", "trim_context")
    g.add_edge("trim_context", "planner")
    g.add_conditional_edges("propose", _after_propose, ["approval", "planner"])
    g.add_edge("approval", "execute")
    g.add_edge("execute", "summarize")
    g.add_edge("summarize", END)
    return g.compile(checkpointer=checkpointer)
