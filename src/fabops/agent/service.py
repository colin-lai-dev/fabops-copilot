"""Run the agent (or the fixed workflow) and resume it after a human decision.

`AgentService.ask()` starts a run; when the graph stops at `approval`, the run is returned as
`awaiting_approval` with the proposal. `AgentService.decide()` resumes the same thread with
`Command(resume=…)`. The approver's id comes from the caller (the API's logged-in user),
never from the LLM.

Checkpoints go to Postgres in normal runs (`postgres_checkpointer`, ADR-0006) and to memory in
tests. Identity is not in the checkpoint: `AgentDeps` is rebuilt for every call.
"""

from __future__ import annotations

import contextlib
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Literal

from langgraph.types import Command

from fabops.agent.gateway import ToolGateway
from fabops.agent.graph import MAX_STEPS, AgentDeps, build_graph
from fabops.agent.proposals import ProposalStore
from fabops.authz.scope import Scope
from fabops.authz.trace import Tracer
from fabops.llm.client import LLMClient

Mode = Literal["agent", "fixed"]


@dataclass
class AgentRun:
    thread_id: str
    mode: Mode
    status: str
    answer: str
    citations: list[str]
    refused: bool
    steps: int
    calls: list[dict[str, Any]]  # {"step", "tool", "args", "ok", "error"?}
    proposal: dict[str, Any] | None
    usage: dict[str, float] = field(default_factory=dict)
    tool_results: list[str] = field(default_factory=list)  # full JSON text, for eval checks


def _run_of(thread_id: str, mode: Mode, values: dict[str, Any], interrupted: bool) -> AgentRun:
    calls = values.get("calls", [])
    return AgentRun(
        thread_id=thread_id,
        mode=mode,
        status="awaiting_approval" if interrupted else values.get("status", "error"),
        answer=values.get("answer", ""),
        citations=values.get("citations", []),
        refused=bool(values.get("refused")),
        steps=values.get("steps", 0),
        calls=[{k: c[k] for k in ("step", "tool", "args", "ok", "error") if k in c} for c in calls],
        proposal=values.get("proposal"),
        usage=values.get("usage", {}),
        tool_results=[c["full"] for c in calls if c.get("ok") and "full" in c],
    )


class AgentService:
    def __init__(
        self,
        llm: LLMClient,
        proposals: ProposalStore,
        checkpointer: Any,
        tracer: Tracer | None = None,
        max_steps: int = MAX_STEPS,
    ):
        self.llm, self.proposals, self.checkpointer = llm, proposals, checkpointer
        self.tracer = tracer or Tracer.from_env()
        self.max_steps = max_steps

    def _graph(self, mode: Mode, deps: AgentDeps):
        return build_graph(deps, mode, checkpointer=self.checkpointer)

    async def ask(
        self,
        question: str,
        *,
        user_id: str,
        scope: Scope,
        gateway: ToolGateway,
        mode: Mode = "agent",
        thread_id: str | None = None,
    ) -> AgentRun:
        thread_id = thread_id or uuid.uuid4().hex[:16]
        deps = AgentDeps(
            self.llm, scope, user_id, gateway, self.proposals, self.tracer,
            await gateway.list_tools(), self.max_steps,
        )  # fmt: skip
        graph = self._graph(mode, deps)
        config = {
            "configurable": {"thread_id": thread_id},
            "recursion_limit": 4 * self.max_steps + 10,
        }
        init = {
            "thread_id": thread_id, "question": question, "mode": mode, "steps": 0, "calls": [],
            "status": "running", "llm_failures": 0, "usage": {},
        }  # fmt: skip
        await graph.ainvoke(init, config)
        snap = await graph.aget_state(config)
        return _run_of(thread_id, mode, snap.values, bool(snap.next))

    async def decide(
        self, thread_id: str, *, approved: bool, approver: str, mode: Mode = "agent", note: str = ""
    ) -> AgentRun:
        """Resume a run waiting at `approval`. No tool or LLM call happens after approval."""
        deps = AgentDeps(
            None, None, approver, None, self.proposals, self.tracer, [], self.max_steps
        )
        graph = self._graph(mode, deps)
        config = {"configurable": {"thread_id": thread_id}}
        snap = await graph.aget_state(config)
        if "approval" not in snap.next:
            raise ValueError(f"run {thread_id} is not waiting for approval")
        cmd = Command(resume={"approved": approved, "approver": approver, "note": note})
        await graph.ainvoke(cmd, config)
        snap = await graph.aget_state(config)
        return _run_of(thread_id, mode, snap.values, bool(snap.next))


@contextlib.asynccontextmanager
async def postgres_checkpointer(database_url: str) -> AsyncIterator[Any]:
    """LangGraph checkpoints in the project Postgres (ADR-0006). On Windows the event loop
    must be a SelectorEventLoop (psycopg async)."""
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

    async with AsyncPostgresSaver.from_conn_string(database_url) as saver:
        await saver.setup()
        yield saver
